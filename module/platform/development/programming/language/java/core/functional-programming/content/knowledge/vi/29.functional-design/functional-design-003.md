# Dùng đối tượng bất biến để truyền kết quả giữa các bước trong Java

## 1. Tại sao thiết kế theo hàm cần đối tượng bất biến?

Trong một quy trình xử lý dữ liệu, kết quả bước trước thường trở thành đầu vào của bước sau. Ví dụ một đơn hàng cần được **nhận dữ liệu → kiểm tra → tính giá → áp dụng chiết khấu → xuất biên nhận**. Có thể tổ chức tất cả các bước cùng sửa một đối tượng trạng thái:

~~~java
// Phác họa một thiết kế có thể gây khó theo dõi:
void calculate(OrderState state) {
    state.total = state.price * state.quantity;
}
void discount(OrderState state) {
    state.total -= 500;
}
~~~

Đây là **mã minh họa không độc lập**: `OrderState` là một class giả định có các field thay đổi được. Vấn đề không phải mọi mutation đều sai, mà là các bước dùng chung reference và **thay đổi cùng một object**. Một lời gọi ở nơi khác có thể quan sát dữ liệu nửa chừng; việc chạy lại một bước có thể cộng phí hai lần; gọi sai thứ tự có thể tạo kết quả khác mà rất khó xác định bước nào đã sửa trạng thái.

Một cách tiếp cận theo hàm là **mỗi bước nhận một giá trị có trạng thái ổn định và trả về một giá trị mới**:

~~~text
Input immutable
      |
      v
validate   : Input -> ValidatedInput
      |
      v
calculate  : ValidatedInput -> PricedInput
      |
      v
discount   : PricedInput -> Receipt
      |
      v
Receipt immutable
~~~

Các giá trị trung gian là các đối tượng biểu diễn *kết quả tại một mốc xử lý*. Không cần tác động lên đối tượng của bước trước để tạo thông tin mới. Với mô hình này, chương trình dễ kiểm thử, dễ quan sát, thuận lợi cho composition và hạn chế race condition khi dữ liệu được chia sẻ đọc giữa các task.

**Mục tiêu bài học:**

1. Hiểu bất biến (immutability) là gì và vì sao hợp với pipeline hàm.
2. Phân biệt **reference không được gán lại**, **object bất biến nông**, **snapshot cấu trúc** và **bất biến sâu**.
3. Dùng `record` Java 17, constructor validation, `List.copyOf` và defensive copy để tạo dữ liệu chuyển giao an toàn.
4. Viết các bước trả kết quả mới, không mutate input; ghép bằng `Function.andThen` hoặc method có tên rõ.
5. Phân biệt bất biến và thuần hàm; xử lý clock, I/O, database, exception, cấu hình và concurrency ở biên phù hợp.
6. Tránh aliasing, “getter rò mutable List”, sử dụng `Collections.unmodifiableList` sai và việc sao chép quá mức.
7. Chạy chương trình Java 17 độc lập với hai trạng thái gốc/mới, tính tiền bằng `long` và kiểm tra validation.
8. Luyện thiết kế các pipeline có dữ liệu và trạng thái chuyển bước tường minh.

## 2. Khái niệm “đối tượng bất biến” chính xác là gì?

### 2.1. Bất biến nhìn từ API

Một **immutable object** là object mà trạng thái có thể quan sát được không thay đổi sau khi tạo trong phạm vi hợp đồng của kiểu đó. Thay vì sửa object, chương trình tạo một giá trị mới có những phần khác biệt.

Ví dụ với `String`:

~~~java
String original = "java";
String upper = original.toUpperCase();

System.out.println(original); // java
System.out.println(upper);    // JAVA
~~~

`toUpperCase()` trả một `String` thay vì sửa `original`. Đây là một cách đơn giản để hình dung “kết quả mới, dữ liệu cũ vẫn có thể sử dụng”.

Với domain object:

~~~java
record Point(int x, int y) {
    Point translated(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
~~~

Đây là một record độc lập có hai component primitive. Lời gọi `new Point(2,3).translated(1,2)` trả một `Point(3,5)`; đối tượng gốc vẫn là `Point(2,3)`. `translated` có thể gọi là một “with-style method”: phương thức tạo một giá trị với thay đổi mong muốn.

### 2.2. `final` trên biến không làm object bất biến

~~~java
final List<String> names = new ArrayList<>();
names.add("An"); // Vẫn hợp lệ.
~~~

`final` ở đây ngăn **gán lại reference** của biến `names`. Nó không cấm gọi `add` trên đối tượng `ArrayList`. Vì vậy không được suy luận “biến final” đồng nghĩa “collection immutable”.

Tương tự, một lambda bắt giữ local effectively final có thể giữ reference đến object mutable; các thread hoặc code khác vẫn có thể sửa object đó. Muốn chia sẻ kết quả an toàn, cần xem **toàn bộ đồ thị dữ liệu quan sát được**, không chỉ modifier của biến.

### 2.3. `record` không tự động bất biến sâu

Java record gọn để biểu diễn dữ liệu, và các component trở thành private final fields với accessor. Nhưng nếu component có kiểu mutable, giá trị được giữ là **tham chiếu đến object đó**.

~~~java
record Team(List<String> names) {}

List<String> original = new ArrayList<>(List.of("An"));
Team team = new Team(original);
original.add("Binh");

System.out.println(team.names()); // [An, Binh]
~~~

Đây là đoạn trong method với import `List` và `ArrayList`. Record `Team` không có setter nhưng trạng thái quan sát được qua `names()` đã đổi! Đây là **aliasing**: object caller và record cùng trỏ tới một List mutable.

Bài học quan trọng: **record là công cụ xây value carrier tốt, nhưng không thay việc kiểm tra và copy các component mutable**.

### 2.4. Bất biến nông và sâu

| Khái niệm | Bảo đảm điển hình | Không tự bảo đảm |
| --- | --- | --- |
| `final` reference | Không gán lại reference local/field đó | Object được trỏ tới bất biến |
| Record với primitive và `String` | Field reference cuối cùng, element cơ bản phù hợp | Nếu thêm object mutable thì cần xét lại |
| `Collections.unmodifiableList(backing)` | Không sửa List qua wrapper | Backing List có thể bị sửa ở nơi khác |
| `List.copyOf(backing)` | Snapshot cấu trúc unmodifiable với dữ liệu không null | Sao chép sâu từng element mutable |
| Model deep immutable | Trạng thái quan sát không đổi cả các component liên quan | Không miễn trừ yêu cầu validation, xử lý lỗi |

“Deep immutable” không có một câu thần chú Java tự tạo; đó là **hợp đồng thiết kế** phụ thuộc kiểu field và reference có thể lọt ra ngoài. Với element chứa `StringBuilder`, `Date`, `byte[]`, List hoặc Map mutable, phải quyết định cách tạo immutable copy, cách trả dữ liệu và có cần deep copy không.

## 3. Các nguyên tắc thiết kế kết quả bất biến giữa các bước

### 3.1. Bước nhận đầu vào và trả kết quả mới

Một hàm chuyển đổi có mô hình:

~~~java
Function<Input, Output> stage = input -> new Output(...);
~~~

Đây là cú pháp khái quát: `Input`, `Output` đại diện cho các kiểu domain thực tế. Bước tốt nên có đầu vào rõ, không sửa object của caller và trả kết quả đủ để bước tiếp theo sử dụng. Việc có kiểu `Function` chưa bảo đảm bất biến; phải xem **thân lambda** và kiểu object.

### 3.2. Mỗi trạng thái chuyển bước có ý nghĩa domain

Thay vì một class có mười cờ `isValidated`, `hasPricing`, `isApproved` và nhiều field có lúc rỗng, có thể dùng những kiểu riêng:

~~~text
Basket
  -> PricedBasket
  -> Receipt
~~~

`Basket` chứa các mặt hàng đã kiểm tra. `PricedBasket` chứa mặt hàng và subtotal. `Receipt` chứa subtotal, discount và total. Bước tính giá không trả về “Basket đã lén thay đổi”, mà trả **một kiểu thông báo trạng thái mới**.

Thiết kế này giúp compiler hạn chế lời gọi sai thứ tự: hàm nhận `PricedBasket` sẽ không được gọi trực tiếp với `Basket` nếu chưa qua bước tạo giá.

### 3.3. Validation ngay tại ranh giới tạo object

Nếu một record biểu diễn “số lượng phải dương”, hãy xác minh trong constructor. Nếu không, một stage có thể nhận object đã sai invariant và trả lỗi muộn hoặc âm thầm tạo giá trị vô nghĩa.

~~~java
record Item(String name, int quantity) {
    Item {
        Objects.requireNonNull(name);
        if (name.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("invalid item");
        }
    }
}
~~~

Đây là record minh họa cần import `java.util.Objects`. Compact constructor của record cho phép kiểm tra hoặc chuẩn hóa component trước khi fields được khởi tạo. Sau đó mọi `Item` tạo hợp lệ qua constructor này có thể được tin cậy về các điều kiện đã kiểm.

### 3.4. Copy dữ liệu mutable khi đi qua biên

Một record nhận `List<Item>` từ caller cần tránh giữ reference tới List mutable bên ngoài:

~~~java
record Basket(List<Item> items) {
    Basket {
        items = List.copyOf(items);
    }
}
~~~

`List.copyOf` trả một List unmodifiable, sao chép nội dung cấu trúc ở thời điểm gọi đối với nguồn mutable như `ArrayList`. Nó từ chối List null và phần tử null. Lưu ý nó **không deep-copy Item**. Vì thế model `Item` trong ví dụ hoàn chỉnh được thiết kế chỉ với `String` và primitive, không có component mutable.

Trong compact constructor, việc gán lại **tham số `items`** là hợp lệ; Java sau đó gán giá trị đã chuẩn hóa cho field record tương ứng. Đây là cách chặn aliasing của List mà không cần viết canonical constructor dài.

## 4. Defensive copy: vào và ra

### 4.1. Copy tại đầu vào là quan trọng

~~~java
List<String> incoming = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(incoming);

incoming.add("B");

System.out.println(snapshot); // [A]
~~~

Ở đây, `snapshot` không phản ánh phần tử `B` được thêm vào List gốc sau khi copy. Nhờ đó, stage downstream nhìn thấy một tập dữ liệu ổn định. Tuy nhiên, nếu thread khác đang mutate `incoming` **ngay trong lúc copy**, chỉ gọi `List.copyOf` không phải giải pháp đồng bộ cho snapshot nhất quán. Cần quản lý quyền sở hữu và synchronization ở biên lấy dữ liệu.

### 4.2. Unmodifiable view không phải snapshot

~~~java
List<String> incoming = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(incoming);

incoming.add("B");

System.out.println(view); // [A, B]
~~~

Wrapper chỉ chặn việc sửa **thông qua `view`**. Nó không ngăn caller giữ `incoming` và mutate từ ngoài. Với dữ liệu giao giữa các bước cần snapshot, view chưa đủ nếu backing source vẫn thay đổi.

### 4.3. Record accessor không phải nơi duy nhất phải kiểm tra

Với `record Basket(List<Item> items)` đã copy bằng `List.copyOf`, accessor `items()` trả List unmodifiable, nên caller không thể `add`/`remove`/`set` thông qua List. Nhưng nếu Item là object mutable, caller vẫn có thể sửa nội dung một Item và các stage đọc được thay đổi. Vì vậy cần rà soát **từng component chứa object mutable**, không chỉ bảo vệ List ở cấp ngoài.

Với mảng, nên dùng copy cả lúc nhận và trả nếu hợp đồng cần:

~~~java
final class Bytes {
    private final byte[] data;

    Bytes(byte[] source) {
        this.data = source.clone();
    }

    byte[] copyData() {
        return data.clone();
    }
}
~~~

Class này minh họa defensive copy ở **cả constructor và getter**. Nếu getter trả `data` trực tiếp, caller sẽ sửa được mảng nội bộ. Mảng không thể trở thành unmodifiable chỉ bằng modifier `final` của field.

### 4.4. Snapshot không có nghĩa mọi object phải khác identity

`List.copyOf` có thể trả lại cùng object nếu đầu vào đã là một List unmodifiable thích hợp. Đừng viết test `copy != original` như một điều kiện của bất biến; hãy kiểm tra **hợp đồng không sửa được và không phản ánh thay đổi cấu trúc từ nguồn mutable** khi phù hợp.

## 5. Thiết kế pipeline kiểu rõ với `record`

Một ví dụ thống nhất:

~~~java
record Item(String name, int quantity, long unitPriceCents) {}
record Basket(List<Item> items) {}
record PricedBasket(List<Item> items, long subtotalCents) {}
record Receipt(
        List<Item> items,
        long subtotalCents,
        long discountCents,
        long totalCents) {}
~~~

Đây là sơ đồ ban đầu cho cấu trúc domain, **chưa có validation/copy đầy đủ**. Trong phần chạy độc lập sẽ thêm constructor kiểm tra dữ liệu và defensive copy. Mục tiêu của từng kiểu:

| Kiểu | Ý nghĩa | Field quan trọng |
| --- | --- | --- |
| `Item` | Dòng hàng đã được kiểm tra | tên, số lượng, đơn giá |
| `Basket` | Giỏ hàng đang dùng làm đầu vào | List mặt hàng |
| `PricedBasket` | Kết quả bước tính giá | List mặt hàng, tổng trước giảm |
| `Receipt` | Kết quả bước hoàn thiện | List mặt hàng, tổng gốc, giảm giá, số phải thanh toán |

Chọn **đơn vị tiền là cents dạng `long`** trong ví dụ để không dạy thói quen dùng `double` cho số tiền. Tuy nhiên, đây vẫn là ví dụ sư phạm, chưa có đồng tiền, thuế, quy tắc làm tròn, chiết khấu phức hợp và bảo đảm nghiệp vụ tài chính đầy đủ.

### 5.1. Tạo đối tượng mới bằng with-style method

Thay vì `basket.items().add(item)`, hãy tạo Basket mới:

~~~java
Basket withAdded(Item item) {
    List<Item> updated = new ArrayList<>(items);
    updated.add(Objects.requireNonNull(item));
    return new Basket(updated);
}
~~~

Đây là **method phải đặt trong record Basket** có component `items` và compact constructor `List.copyOf(items)`. Dữ liệu `items` cũ không đổi. Danh sách mới được tạo trong phạm vi method, sau đó constructor chuẩn hóa thành snapshot unmodifiable.

Đối với collection lớn, copy toàn bộ List mỗi lần thêm có thể tốn tài nguyên; phần hiệu năng bên dưới trình bày cách chọn lúc nào cần copy và lúc nào nên dùng cấu trúc dữ liệu khác.

### 5.2. Biểu diễn lỗi nhất quán

Bất biến không có nghĩa không có exception. Constructor có thể ném `IllegalArgumentException` nếu số lượng không hợp lệ, hoặc `Math.multiplyExact` ném `ArithmeticException` nếu phép nhân overflow. Đây là cách **phát hiện và báo lỗi** chứ không để tạo object trạng thái sai.

Nếu ứng dụng cần thu thập lỗi validation thay vì fail-fast, có thể thiết kế kiểu `ValidationResult<T>` hoặc sealed interface giữa `Success` và `Failure`. Khi đó lỗi trở thành dữ liệu bất biến, được truyền qua pipeline giống kết quả bình thường. Không nhất thiết phải biến mọi lỗi thành exception.

## 6. Bước xử lý là phép biến đổi có kiểu

### 6.1. Tính subtotal

Bước đầu có thể có kiểu:

~~~java
Function<Basket, PricedBasket> price = basket -> {
    long subtotal = basket.items().stream()
            .mapToLong(Item::lineTotalCents)
            .reduce(0L, Math::addExact);
    return new PricedBasket(basket.items(), subtotal);
};
~~~

Ở đây `Item::lineTotalCents` phải là method tính `long` của record `Item`. `Math.addExact` làm rõ chính sách **không im lặng cho phép overflow**. `0L` là identity cho phép cộng, và việc cộng các `long` không vượt miền hợp lệ tạo kết quả mong đợi.

**Không có lệnh sửa Basket**. Lambda nhận Basket, đọc item, tính subtotal rồi tạo PricedBasket mới. Điều này làm luồng dữ liệu dễ theo dõi: subtotal gắn với đúng tập item ở thời điểm tạo object.

### 6.2. Hoàn thiện giảm giá

~~~java
Function<PricedBasket, Receipt> discount = priced -> {
    long amount = Math.min(priced.subtotalCents(), 500L);
    long total = Math.subtractExact(
            priced.subtotalCents(), amount);
    return new Receipt(
            priced.items(),
            priced.subtotalCents(),
            amount,
            total);
};
~~~

Đây là mảnh mã trong class có records và import `Function`. Quy tắc “giảm tối đa 500 cents” chỉ để minh họa; mỗi lần tính từ `PricedBasket`, bước giảm không mutate chính object `PricedBasket`. Nếu muốn giữ giá trị lịch sử cho audit, có thể lưu các object kết quả mà không sợ một stage tiếp theo sửa List của chúng qua API chuẩn.

### 6.3. Ghép các bước bằng `Function.andThen`

~~~java
Function<Basket, PricedBasket> price = ...;
Function<PricedBasket, Receipt> discount = ...;

Function<Basket, Receipt> pipeline =
        price.andThen(discount);

Receipt receipt = pipeline.apply(basket);
~~~

Đây là **sơ đồ gõ kiểu**, `...` đại diện implementations ở hai mục trước. `price.andThen(discount)` đòi output của `price` tương thích input của `discount`. Compiler giúp phát hiện việc ghép nhầm stage. Trên thực tế, có thể khai báo các stage là method thường và dùng method reference `MyClass::price` để tránh lưu state không cần thiết.

`Function.andThen` không tự bảo đảm kết quả bất biến. Nếu `price` trả cùng object mutable đã sửa, pipeline vẫn có side effect. **Tính bất biến là đặc tính của model và cách viết stage**, không phải do chỉ có API composition.

## 7. Chương trình Java 17 hoàn chỉnh

Ví dụ tạo `Basket` từ một `ArrayList` đầu vào; sửa ArrayList sau đó để chứng minh snapshot không đổi. Tiếp theo, một pipeline tính giá rồi giảm giá tạo `Receipt`. Ta cũng tạo Basket mới bằng with-style method, kiểm tra Basket gốc vẫn giữ nguyên và thử một thao tác sửa bị chặn.

Tạo tệp **`ImmutablePipelineDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class ImmutablePipelineDemo {

    record Item(String name, int quantity, long unitPriceCents) {
        Item {
            Objects.requireNonNull(name, "name");
            if (name.isBlank() || quantity <= 0 || unitPriceCents < 0) {
                throw new IllegalArgumentException("invalid item");
            }
        }

        long lineTotalCents() {
            return Math.multiplyExact(
                    (long) quantity, unitPriceCents);
        }
    }

    record Basket(List<Item> items) {
        Basket {
            items = List.copyOf(items);
        }

        Basket withAdded(Item item) {
            List<Item> updated = new ArrayList<>(items);
            updated.add(Objects.requireNonNull(item));
            return new Basket(updated);
        }
    }

    record PricedBasket(List<Item> items, long subtotalCents) {
        PricedBasket {
            items = List.copyOf(items);
        }
    }

    record Receipt(
            List<Item> items,
            long subtotalCents,
            long discountCents,
            long totalCents) {
        Receipt {
            items = List.copyOf(items);
        }
    }

    static final Function<Basket, PricedBasket> PRICE = basket -> {
        long subtotal = basket.items().stream()
                .mapToLong(Item::lineTotalCents)
                .reduce(0L, Math::addExact);

        return new PricedBasket(basket.items(), subtotal);
    };

    static final Function<PricedBasket, Receipt> DISCOUNT = priced -> {
        long discount = Math.min(priced.subtotalCents(), 500L);
        long total = Math.subtractExact(
                priced.subtotalCents(), discount);

        return new Receipt(
                priced.items(),
                priced.subtotalCents(),
                discount,
                total);
    };

    public static void main(String[] args) {
        List<Item> incoming = new ArrayList<>(List.of(
                new Item("Book", 2, 1200L),
                new Item("Pen", 1, 300L)
        ));

        Basket original = new Basket(incoming);

        // Sửa List đầu vào sau khi tạo Basket.
        incoming.add(new Item("External", 1, 999L));

        Function<Basket, Receipt> pipeline =
                PRICE.andThen(DISCOUNT);

        Receipt receipt = pipeline.apply(original);

        Basket updated = original.withAdded(
                new Item("Notebook", 1, 4000L));

        Receipt updatedReceipt = pipeline.apply(updated);

        System.out.println(
                "originalItems=" + original.items().stream()
                        .map(Item::name)
                        .toList());

        System.out.println(
                "receipt=" + receipt.subtotalCents()
                        + "/" + receipt.discountCents()
                        + "/" + receipt.totalCents());

        System.out.println(
                "updatedItems=" + updated.items().stream()
                        .map(Item::name)
                        .toList());

        System.out.println(
                "updatedTotal=" + updatedReceipt.totalCents());

        System.out.println(
                "originalStill=" + original.items().size());

        try {
            original.items().add(
                    new Item("CannotAdd", 1, 1L));
        } catch (UnsupportedOperationException ex) {
            System.out.println("listMutation=blocked");
        }

        try {
            new Item("Invalid", 0, 100L);
        } catch (IllegalArgumentException ex) {
            System.out.println("validation=rejected");
        }
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 ImmutablePipelineDemo.java
java ImmutablePipelineDemo
~~~

**Stdout chính xác:**

~~~text
originalItems=[Book, Pen]
receipt=2700/500/2200
updatedItems=[Book, Pen, Notebook]
updatedTotal=6200
originalStill=2
listMutation=blocked
validation=rejected
~~~

### 7.1. Vì sao sửa `incoming` không thay `original`?

`Basket` dùng `List.copyOf(items)` khi xây dựng. Vì vậy `incoming.add(new Item("External",...))` chỉ thay đổi ArrayList thuộc caller, không làm Basket tự có thêm mặt hàng. `originalItems` chỉ gồm Book và Pen.

### 7.2. Tính giá gốc diễn ra thế nào?

- Book: `2 * 1200 = 2400` cents.
- Pen: `1 * 300 = 300` cents.
- Subtotal: `2400 + 300 = 2700` cents.
- Discount theo chính sách minh họa: `min(2700,500)=500` cents.
- Total: `2700 - 500 = 2200` cents.

Không có bước nào sửa một field subtotal của Basket; `PricedBasket` và `Receipt` là **giá trị mới** có component tương ứng.

### 7.3. Vì sao Basket mới có ba món nhưng Basket gốc vẫn hai?

`withAdded` tạo một ArrayList mới từ `items` cũ, thêm Notebook rồi xây Basket mới. `updated` có Book, Pen, Notebook; `original` vẫn chỉ có Book và Pen. Subtotal mới `2700 + 4000 = 6700` cents; giảm `500` nên `updatedTotal=6200`.

Điều này giúp giữ giá trị quá khứ để test, so sánh và debug, đồng thời tránh việc một stage mutate kết quả của stage trước.

### 7.4. Vì sao `listMutation=blocked`?

Accessor `original.items()` trả List unmodifiable được lưu sau `List.copyOf`. `add` không được hỗ trợ và ném `UnsupportedOperationException`. Đây là bảo vệ **cấu trúc List**, không phải bảo đảm thần kỳ mọi object phần tử đều immutable; ví dụ `Item` của bài có String và primitive nên bản thân các field không cho mutate trạng thái thông qua API của record.

### 7.5. Vì sao `validation=rejected`?

`Item` yêu cầu `quantity > 0`. Khi tạo `new Item("Invalid",0,100L)`, compact constructor ném `IllegalArgumentException`. Nhờ validation tại nơi tạo value object, pipeline không phải đoán liệu một Item hợp lệ hay không ở mọi bước. Đây là một dạng **fail fast** có chủ đích.

## 8. Tính bất biến và hàm thuần: liên quan nhưng khác nhau

### 8.1. Pure function là gì?

Một hàm thuần (pure function) thường có hai đặc điểm:

1. Cùng giá trị đầu vào → cùng giá trị đầu ra theo ngữ nghĩa cần quan sát.
2. Không tạo side effect có thể quan sát ngoài kết quả trả về.

Ví dụ `price(Basket)` với dữ liệu và policy cố định có thể gần mô hình này: đọc Basket immutable, tính subtotal và trả PricedBasket mới. Nếu đầu vào hợp lệ, không overflow và không có I/O, kết quả ổn định.

### 8.2. Dùng immutable object không tự biến một stage thành pure

~~~java
Function<Basket, Receipt> stage = basket -> {
    auditService.sendEvent("pricing");
    return calculateReceipt(basket);
};
~~~

Đây là **mã minh họa không độc lập**, có `auditService` và `calculateReceipt` giả định. Dù Basket và Receipt là immutable, lời gọi gửi sự kiện là side effect. Hàm không còn thuần theo nghĩa trên. Đổi sang record không loại bỏ tương tác database, clock, random hoặc HTTP.

Điều thực tế là **giữ side effects ở ranh giới rõ ràng**: đọc dữ liệu vào model, thực hiện phần lớn biến đổi thuần, rồi ghi/lưu/publish kết quả qua một adapter riêng.

### 8.3. Clock, random và cấu hình nên là đầu vào rõ

Nếu một stage đọc `Instant.now()` ở bên trong, cùng Basket ở hai lần gọi có thể sinh timestamp khác. Nếu domain cần thời gian, có thể truyền thời điểm vào request immutable hoặc inject `Clock` trong API thích hợp:

~~~java
record PricingRequest(Basket basket, Instant requestedAt) {}

PricingRequest request = new PricingRequest(
        basket, clock.instant());
~~~

Đây là **mảnh mã minh họa** với biến `basket`/`clock` đã có, import `java.time.Instant` và `Clock`. Khi request đã giữ timestamp, các bước tính toán bên trong có thể dùng cùng một giá trị, tránh đọc clock nhiều lần gây khác biệt.

Tương tự, cấu hình thuế, tỷ lệ chiết khấu hoặc locale nên được biểu diễn bằng value object ổn định cho một lần xử lý; nếu stage đọc mutable singleton mỗi lần gọi, dữ liệu kết quả có thể phụ thuộc vào timing.

## 9. Lợi ích của kết quả bất biến trong workflow

### 9.1. Dễ hiểu thứ tự và trách nhiệm

Thay vì một object bị thay đổi qua nhiều method, mỗi kết quả thể hiện ý nghĩa tại một giai đoạn. Khi lỗi xảy ra ở bước giảm giá, có thể kiểm tra lại `PricedBasket` mà không lo chính bước sau đã sửa subtotal ban đầu.

### 9.2. Dễ unit test riêng từng bước

~~~java
Basket basket = new Basket(List.of(
        new Item("Book", 2, 1200L)));

PricedBasket result = PRICE.apply(basket);

assert result.subtotalCents() == 2400L;
assert basket.items().size() == 1;
~~~

Đây là mảnh mã trong ngữ cảnh class demo; từ khóa `assert` của Java mặc định bị tắt trừ khi chạy với `-ea`. Với bộ test dự án, nên dùng JUnit assertion rõ ràng. Không chỉ kiểm tra subtotal; nên kiểm tra **đầu vào không bị thay đổi**.

### 9.3. Thuận lợi để cache khi phù hợp

Nếu value object có ý nghĩa equality ổn định và stage thuần, có thể xây cache theo key bất biến. Record cung cấp `equals`/`hashCode` theo component, thuận lợi trong nhiều trường hợp. Nhưng record chứa List mutable hoặc object mutable vẫn có thể làm key thay đổi ngữ nghĩa, phá cache.

**Bất biến không tự tạo memoization.** Nếu không có cache được thiết kế, mỗi lần gọi `PRICE.apply(basket)` vẫn chạy phép tính. Cần cân nhắc vòng đời, memory, key, invalidation và concurrency riêng.

### 9.4. Giảm nhu cầu khóa khi chỉ đọc

Nếu nhiều thread cùng đọc một object thực sự immutable, không phải phối hợp mutation trên object ấy. Đây là lợi ích quan trọng của kết quả bất biến cho concurrency hoặc parallel pipelines.

Nhưng **bất biến không đồng nghĩa toàn bộ workflow thread-safe**: side effect ghi database, log, object mutable bên trong hoặc chia sẻ bộ nhớ không an toàn ở biên vẫn cần xem xét. Hãy bảo đảm object được tạo/đưa tới thread khác qua cơ chế publication phù hợp; với các final fields được xây dựng đúng và không để `this` thoát trong constructor, Java có những bảo đảm riêng về final-field semantics.

## 10. Áp dụng trong Stream: transform thay vì mutate

### 10.1. Pipeline biến đổi thành kết quả mới

~~~java
List<Item> adjusted = items.stream()
        .map(item -> new Item(
                item.name(),
                item.quantity(),
                Math.addExact(item.unitPriceCents(), 100L)))
        .toList();
~~~

Đây là mảnh mã với `items` kiểu `List<Item>` và record `Item` trong bài. Mỗi phần tử được **thay bằng một Item mới** có giá tăng 100 cents, thay vì sửa Item gốc. `Stream.toList()` trả List unmodifiable trên Java 17.

Cần lưu ý: tăng giá có thể overflow hoặc vi phạm chính sách nghiệp vụ; `Math.addExact` báo lỗi thay vì silent wrap. Phép biến đổi trong ví dụ dùng object immutable, không thay đổi List nguồn.

### 10.2. Không mutate nguồn trong `map` hoặc `peek`

Anti-pattern:

~~~java
items.stream()
        .map(item -> {
            item.setPrice(...);
            return item;
        });
~~~

Đây là mã **phản diện không độc lập**: `Item` trong ví dụ là record nên không có `setPrice`. Trên object mutable thực tế, việc sửa phần tử đang duyệt có thể làm các pipeline khác dùng chung object quan sát trạng thái thay đổi. Đặc biệt với Stream song song, callback mutate shared objects có thể gây race.

Để truyền dữ liệu từ bước trước đến sau, nên trả object mới từ `map`. Nếu nghiệp vụ thật sự đòi mutation, hãy quản lý ở ranh giới rõ và đừng giả định Stream tự giải quyết đồng bộ.

### 10.3. `Collectors.toList()` không hứa immutable

~~~java
List<Item> collected = items.stream()
        .collect(Collectors.toList());
~~~

Theo Javadoc, `Collectors.toList()` **không cam kết kiểu triển khai, mutability, serializability hoặc thread safety**. Nếu bước sau cần một snapshot cấu trúc không cho sửa, dùng `Stream.toList()` trên Java 17, `Collectors.toUnmodifiableList()` khi null không được chấp nhận hoặc `List.copyOf` tại ranh giới phù hợp.

`Stream.toList()` có thể chứa `null`, còn `List.copyOf` và `Collectors.toUnmodifiableList()` từ chối `null`. Đừng thay các API chỉ vì tên gần nhau; xác định yêu cầu về null và loại List.

## 11. Quản lý trạng thái cập nhật: wither và versioned values

### 11.1. Wither tạo bản mới thay vì setter

Ví dụ:

~~~java
record UserProfile(String name, String city) {
    UserProfile withCity(String nextCity) {
        return new UserProfile(name, nextCity);
    }
}
~~~

Trong trường hợp này, `withCity` tạo một `UserProfile` khác còn object gốc giữ nguyên. Nếu field là List, Map, array hoặc object mutable, vẫn phải copy/validate tương ứng. Tên “withCity” chỉ mô tả ý định; compiler không kiểm tra phương thức có thuần hay không.

### 11.2. Chuyển trạng thái thành giá trị có phiên bản

Khi cập nhật workflow nhiều bước, có thể dùng:

~~~java
record Versioned<T>(long version, T value) {}
~~~

Đây là kiểu dữ liệu minh họa để mang version và payload. Một phiên bản mới có thể được biểu diễn bằng `new Versioned<>(old.version()+1, nextValue)` thay vì mutate cùng holder. Tuy nhiên, **record generic không buộc `T` immutable**. Nếu T là ArrayList mutable, version không tự bảo vệ dữ liệu.

Trong hệ thống có database, version có thể hỗ trợ optimistic concurrency control khi được kiểm tra/ghi bằng transaction phù hợp; chỉ tăng số trong object Java không chống được race giữa nhiều request hay tiến trình.

### 11.3. Tránh object trung gian “nửa hợp lệ”

Khi mỗi stage dùng một kiểu riêng, một `PricedBasket` không cần có field `paidAt` chưa được gán, còn `Receipt` không cần mang cờ `pricingDone`. Điều này giúp biểu diễn các trạng thái hợp lệ bằng type thay vì một object với rất nhiều field nullable.

Tuy nhiên, không phải quy trình nào cũng cần một record mới cho mỗi lệnh nhỏ. Chọn stage type theo **ranh giới nghiệp vụ có ý nghĩa**, tránh overengineering bằng hàng chục lớp chỉ khác nhau một field.

## 12. Validation, exception và dữ liệu lỗi

### 12.1. Bất biến cần invariant đúng từ lúc khởi tạo

Nếu `Receipt` ghi total, subtotal, discount, các giá trị đó phải tương thích. Trong ví dụ hoàn chỉnh, pipeline tạo total bằng `Math.subtractExact`, nhưng record `Receipt` chỉ thực hiện defensive copy và chưa kiểm tra toàn bộ quan hệ tài chính. Trong hệ thống thật, constructor hoặc factory nên kiểm tra:

- `subtotalCents >= 0` và `discountCents >= 0`.
- Chiết khấu không vượt subtotal, trừ khi domain có chính sách credit khác.
- `totalCents` khớp đúng quy tắc tính toán và rounding.
- Currency và scale, thuế/phí, quyền truy cập và validation của đầu vào.
- Các line item thuộc đơn hàng có thể đối chiếu với subtotal theo nguồn dữ liệu nào.

Việc dùng record không tự chứng minh mọi invariant trên. Thiết kế DTO cần tập trung vào độ đúng của domain, không chỉ vào syntax ngắn.

### 12.2. Một cách biểu diễn lỗi bất biến

Trong API cần gom nhiều lỗi, có thể dùng sealed type:

~~~java
sealed interface Outcome<T>
        permits Success, Failure {}

record Success<T>(T value) implements Outcome<T> {}

record Failure<T>(String message)
        implements Outcome<T> {}
~~~

Đây là mảnh mã Java 17 minh họa; `message` nên được validate nếu domain yêu cầu. `Success<T>` **không đảm bảo T bất biến**; payload phải được lựa chọn hoặc snapshot theo hợp đồng. Stage có thể trả `Outcome<Receipt>`: caller xử lý thành công hoặc thất bại mà không cần mutate một object `ProcessState` nhiều cờ.

### 12.3. Không phải lỗi nào cũng nên biến thành dữ liệu

Với bug, lỗi invariant hoặc resource failure, exception vẫn có vai trò. Mục tiêu là giữ **hợp đồng của từng bước rõ ràng**. Nếu chọn exception, không nuốt `IOException` hoặc lỗi tính toán rồi trả một Receipt có số 0 giả như thành công.

Cả việc dùng exception hay kiểu `Outcome` đều tương thích với kết quả bất biến, miễn side effects và trạng thái được xử lý nhất quán.

## 13. Concurrency, sharing và parallel Stream

### 13.1. Value object giúp chia sẻ dữ liệu đọc

Một `Basket` thực sự bất biến có thể được dùng làm nguồn cho nhiều phép tính đọc mà không đòi đồng bộ mutation trên chính Basket. Với pipeline song song:

~~~java
long subtotal = basket.items().parallelStream()
        .mapToLong(Item::lineTotalCents)
        .reduce(0L, Math::addExact);
~~~

Vì các Item trong ví dụ là immutable, callback không sửa source và phép cộng nguyên có identity `0L`, pipeline biểu diễn reduction hợp lệ khi các phép tính không overflow. `Math.addExact` có thể ném lỗi nếu một partial sum vượt giới hạn, nên thiết kế phải có chính sách cho miền dữ liệu và chi phí, không đơn thuần “parallel là chính xác hơn”.

### 13.2. Bất biến và stateless lambda là hai yêu cầu khác nhau

Ngay cả khi input immutable, callback có thể gây side effect:

~~~java
AtomicInteger counter = new AtomicInteger();

basket.items().parallelStream()
        .map(item -> {
            counter.incrementAndGet();
            return item;
        });
~~~

Đây là đoạn anti-pattern (và chưa có terminal operation): việc dùng shared `AtomicInteger` khiến callback stateful; tăng atomic không thay đổi sự thật nó có side effect. Với tối ưu hóa Stream, một số intermediate operations có thể không được gọi nếu kết quả không yêu cầu. Không dùng side effect trong `map` làm bộ đếm nghiệp vụ.

Nếu cần số lượng mặt hàng, `basket.items().size()` hoặc `stream().count()` rõ hơn. Nếu cần tổng số lượng, dùng `mapToInt(Item::quantity).sum()` và kiểm soát overflow.

### 13.3. Không mặc định các collection bên ngoài thread-safe

`List.copyOf` trả List không sửa được về cấu trúc, nhưng chỉ giúp chia sẻ an toàn nếu phần tử/nguồn đã được tạo ổn định và dùng đúng hợp đồng. Việc kết nối database, gọi HTTP, ghi log, cập nhật cache hoặc mutate object nội bộ khác vẫn có thể đòi synchronization, transaction hay idempotency.

### 13.4. Chạy song song chỉ khi có lợi ích

Với Basket vài Item và phép nhân/cộng đơn giản, `parallelStream()` thường làm tăng overhead. Viết pipeline tuần tự trước, kiểm thử tính đúng, đo workload thực tế; chỉ chọn parallel nếu có dữ liệu đủ lớn, hàm tính toán độc lập và lợi ích đo được.

## 14. Chi phí và giới hạn của thiết kế bất biến

### 14.1. Copy List có chi phí

`List.copyOf` và tạo List mới trong `withAdded` có thể tốn O(n) khi cần copy cấu trúc của `n` phần tử. Nếu mỗi thay đổi một phần tử đều tạo bản sao toàn bộ danh sách dài hàng triệu mục, chi phí CPU/bộ nhớ có thể lớn.

Điều này không làm kỹ thuật sai, nhưng đòi lựa chọn hợp lý:

- Với DTO nhỏ và số lần cập nhật ít, defensive copy thường đơn giản, dễ chứng minh đúng.
- Với batch updates, có thể tích lũy nội bộ bằng mutable builder **riêng một scope**, rồi publish một snapshot immutable sau khi hoàn tất.
- Với dữ liệu lớn và nhiều version, cân nhắc persistent data structures có structural sharing (qua thư viện phù hợp), thay vì tự deep-copy toàn bộ ở mỗi bước.
- Với domain không cần chia sẻ snapshot, một cấu trúc mutable được quản lý quyền sở hữu có thể hợp lý hơn.

### 14.2. Structural sharing chỉ an toàn nếu phần được chia sẻ bất biến

Hai version có thể dùng chung phần dữ liệu đã bất biến thay vì copy tất cả. Nhưng nếu cả hai version cùng trỏ tới một component mutable và một nơi sửa nó, tính ổn định của snapshot bị phá vỡ. Structural sharing là tối ưu đúng **sau khi** xác lập contract của từng node/component.

### 14.3. Không phải pipeline nào cũng cần record riêng cho từng bước

Nếu ba bước chỉ chuyển đổi `String` thuần, việc tạo ba record `ValidatedString`, `NormalizedString` và `FinalString` có thể làm code khó đọc hơn mà không thêm nhiều giá trị. Hãy dùng domain types khi chúng biểu diễn invariant, ranh giới trách nhiệm, thông tin lỗi hoặc metadata quan trọng. Sự rõ ràng và tính đúng quan trọng hơn số lượng record.

## 15. Lỗi phổ biến và cách khắc phục

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| Nghĩ `final List` làm List immutable | Chỉ reference final; object vẫn có thể sửa | Dùng copy/view phù hợp và kiểm soát owner |
| Dùng record có `List` mà không copy | Bên ngoài mutate List làm record thay đổi | `List.copyOf` trong constructor |
| Dùng `Collections.unmodifiableList(source)` thay snapshot | Wrapper vẫn phản ánh mutation backing | `List.copyOf` khi cần snapshot |
| Nghĩ `List.copyOf` deep-copy Item | Element mutable vẫn thay đổi | Element immutable hoặc deep copy phù hợp |
| Getter trả `byte[]` nội bộ | Caller mutate mảng bên trong | Trả clone/copy |
| Dùng `Collectors.toList()` rồi tuyên bố List bất biến | API không cam kết mutability | `Stream.toList()`/`List.copyOf` theo yêu cầu |
| Để object input bị mutate trong stage | Bước sau và bước trước dùng chung state | Trả object mới với component rõ |
| Dùng `andThen` rồi nghĩ callback tự thuần | Composition không chặn side effect | Review logic và data types |
| Đọc clock/random/config mutable trong stage | Cùng input có thể khác output | Truyền thông tin cố định vào request |
| Không validate khi tạo record | Có thể publish object trạng thái sai | Compact constructor/factory có invariant |
| Dùng `long` rồi nghĩ tiền không bao giờ overflow | Vẫn có giới hạn biểu diễn | `Math.addExact`, `multiplyExact` và policy miền |
| Copy data trong lúc thread khác mutate nguồn | Snapshot có thể không nhất quán | Đồng bộ/transaction tại ranh giới |
| Mỗi bước deep-copy mọi thứ vô điều kiện | Tốn bộ nhớ/CPU | Copy đúng ranh giới, cân nhắc structural sharing |
| Dùng mutable field trong record làm Map key | `hashCode`/`equals` ngữ nghĩa có thể đổi | Chỉ dùng component ổn định cho key |
| Cho rằng immutable object bảo đảm toàn hệ thống thread-safe | I/O, cache, DB, callback vẫn có state | Đồng bộ các tác dụng phụ riêng |

## 16. Bài tập thực hành

### Bài 1 — Sửa record rò mutable List

Cho:

~~~java
record Team(List<String> members) {}
~~~

Tạo ArrayList, xây Team rồi thêm người vào ArrayList. Giải thích vì sao Team quan sát thay đổi. Viết compact constructor với `members = List.copyOf(members);`, thử lại và xác minh list trả bởi accessor không `add` được. Nếu List chứa element mutable thì sao?

### Bài 2 — Viết wither không mutate input

Thiết kế `record UserProfile(String name,String city)` với `withCity(String newCity)`. Tạo `original`, `updated`, in cả hai và chứng minh original giữ city cũ. Thêm validation city không blank nếu hợp đồng yêu cầu.

### Bài 3 — Thiết kế stage types

Định nghĩa `RawOrder`, `ValidatedOrder`, `PricedOrder`. Viết `Function<RawOrder,ValidatedOrder>` và `Function<ValidatedOrder,PricedOrder>`, ghép `andThen` rồi kiểm tra kiểu đầu vào/đầu ra. Giải thích compiler giúp chặn gọi một bước pricing khi chưa validate thế nào.

### Bài 4 — Snapshot và view

Tạo ArrayList `["A"]`, tạo `Collections.unmodifiableList(source)` và `List.copyOf(source)`, sau đó thêm `"B"` vào source. Quan sát view `[A,B]` nhưng snapshot `[A]`. Mô tả khi nào mỗi loại có ý nghĩa.

### Bài 5 — Immutable List nhưng mutable element

Tạo `record Payload(List<StringBuilder> values)` có compact constructor `List.copyOf`. Sau khi tạo, gọi `append` trên một `StringBuilder` được giữ từ bên ngoài. Giải thích vì sao payload vẫn quan sát thay đổi, rồi đề xuất model với `List<String>` được copy từ `builder.toString()` tại biên.

### Bài 6 — Refactor một pipeline có mutable state

Cho một `OrderState` có setter `setSubtotal`, `setDiscount`, `setTotal`. Thiết kế lại thành `Basket -> PricedBasket -> Receipt`, mỗi stage trả object mới. Kiểm tra input trước và sau pipeline bằng các phép so sánh giá trị, không chỉ bằng reference identity.

### Bài 7 — Bất biến và thời gian

Một hàm nhận Basket nhưng tự gọi `Instant.now()` rồi thêm thời gian vào Receipt. Cùng Basket cho nhiều Receipt khác nhau. Hãy sửa bằng cách truyền `Instant` vào request hoặc inject `Clock`; kiểm thử bằng thời điểm cố định, xác định phần nào còn side effect.

### Bài 8 — Overflow và validation

Thử `Item` có `quantity=0`, `unitPriceCents=-1` hoặc name blank. Kiểm tra constructor từ chối. Thử `Math.multiplyExact` với hai số tạo tích vượt giới hạn `long`; giải thích vì sao không được biến overflow thành một tổng âm tưởng như hợp lệ.

### Bài 9 — Kết quả lỗi bất biến

Định nghĩa sealed `Outcome<T>` gồm `Success<T>` và `Failure<T>`. Viết stage kiểm tra một request; trường hợp hợp lệ trả Success chứa một value object immutable, trường hợp không hợp lệ trả Failure mô tả lỗi. Nêu giới hạn: generic T có thể là mutable object nếu caller tự truyền vào.

### Bài 10 — Đánh giá chi phí copy

Cho Basket chứa hàng chục nghìn Item và 1.000 lần gọi `withAdded`. Phân tích chi phí O(n) sao chép mỗi bước; đề xuất builder cho một batch cập nhật rồi publish snapshot, hoặc cấu trúc persistent có structural sharing phù hợp. Không tối ưu hóa theo cảm giác: đo trên workload mục tiêu.

### Bài 11 — Parallel Stream và sharing

Dùng `Basket` với List<Item> thực sự immutable để tính tổng bằng `parallelStream().mapToLong(...).reduce(0L,Math::addExact)`. So sánh với tuần tự trên dữ liệu nhỏ hợp lệ. Sau đó tạo callback cập nhật ArrayList chung và giải thích tại sao **List input bất biến không đủ** để làm side effect ấy an toàn.

## 17. Câu hỏi tự kiểm tra

**1. “Đối tượng bất biến” có nghĩa gì?** Trạng thái quan sát được theo hợp đồng không thay đổi sau khi tạo.

**2. Biến local `final List` có làm List immutable không?** Không, final chỉ ngăn gán lại reference.

**3. `record` có đảm bảo mọi component immutable sâu?** Không; List/Map/array/object mutable cần xử lý riêng.

**4. `List.copyOf` giải quyết điều gì?** Tạo List unmodifiable với snapshot cấu trúc thích hợp, từ chối null, không deep-copy element.

**5. `Collections.unmodifiableList` khác `List.copyOf` ra sao?** Wrapper view có thể phản ánh thay đổi backing; copy tạo snapshot cấu trúc.

**6. Một stage tốt làm gì?** Nhận dữ liệu có hợp đồng rõ và trả một kết quả mới, không sửa input khi thiết kế theo hàm yêu cầu điều đó.

**7. `Function.andThen` có tự đảm bảo bất biến không?** Không; loại model và thân hàm quyết định.

**8. `Item` trong chương trình có những invariant nào?** Tên không null/không blank, số lượng dương, đơn giá không âm.

**9. Vì sao dùng `Math.multiplyExact`/`addExact`?** Để phát hiện overflow thay vì âm thầm cho kết quả wrap.

**10. Bất biến có đồng nghĩa hàm thuần?** Không; stage vẫn có thể gọi I/O, clock hoặc mutate state ngoài.

**11. Bất biến có giúp concurrency không?** Có, nhờ giảm nguy cơ shared mutable state khi chỉ đọc; không tự giải quyết mọi vấn đề publication và side effects.

**12. Có nên copy List ở mọi bước?** Không nhất thiết; chọn điểm snapshot/ownership hợp lý và đánh giá chi phí.

## 18. Checklist thiết kế trước khi publish một kết quả

1. Kết quả mới có **kiểu domain** thể hiện đúng trạng thái xử lý không?
2. Có còn setter hoặc public mutable field nào cho phép sửa kết quả sau khi tạo không?
3. Component nào là object mutable (List, Map, array, Date, StringBuilder, domain object)?
4. Constructor đã defensive-copy những component cần snapshot chưa?
5. Getter có vô tình trả mutable internal array/collection không?
6. Collection được trả có bảo đảm unmodifiable? Có xử lý null và mutable elements phù hợp?
7. Validation/invariant đã nằm tại ranh giới tạo object chưa?
8. Stage có sửa input/source hoặc mutate shared state ngoài object mới không?
9. Có phụ thuộc clock, random, I/O hoặc cấu hình thay đổi đồng thời không? Có thể truyền dữ liệu ổn định vào request không?
10. Có kiểm soát overflow/đơn vị/rounding cho số lượng và tiền không?
11. Khi exception xảy ra giữa pipeline, object trước đó có còn dùng được không? Có side effect nào cần bù trừ không?
12. Khi chia sẻ object giữa thread, liệu các component có thực sự ổn định và được publish đúng cách không?
13. Việc tạo object mới có khiến copy quá nhiều trên dataset lớn không? Có cần builder theo batch hoặc structural sharing không?
14. Test có kiểm tra input **không đổi**, output đúng, validation, null, và khả năng sửa List bị chặn không?

## 19. Tổng kết và tài liệu tham khảo

**Thiết kế theo hàm thường truyền giá trị bất biến giữa các bước: `Input -> Validated -> Priced -> Result`.** Mỗi bước đọc một trạng thái ổn định và tạo đối tượng kết quả mới, thay vì sửa một holder chung. Cách này làm code dễ hiểu, dễ kiểm thử, thuận lợi cho composition và giảm lỗi do shared mutable state.

Trong Java 17, `record` rất phù hợp để mô hình hóa dữ liệu chuyển bước, nhưng **record không tự bất biến sâu**. Hãy dùng compact constructor để validate và defensive copy List/Map cần thiết; `List.copyOf` tạo snapshot cấu trúc unmodifiable nhưng không deep-copy element, còn `Collections.unmodifiableList` là view có thể phản ánh mutation từ backing source. Với array, copy cả khi nhận và khi xuất nếu cần.

Bất biến **không tự động tạo hàm thuần hay bảo đảm toàn hệ thống thread-safe**: clock, I/O, database, shared cache, exception và publication vẫn cần thiết kế rõ. Đừng copy mù quáng: khi dữ liệu lớn, đánh giá chi phí và chọn ranh giới ownership/snapshot đúng, có thể dùng mutable builder nội bộ rồi publish một giá trị bất biến. Quan trọng nhất là **dữ liệu bước trước không bị thay đổi ngoài ý muốn khi tạo kết quả của bước tiếp theo**.

**Tài liệu chuẩn để tra cứu:** Javadoc Java SE 17 của `java.lang.Record`, `java.util.List.copyOf`, `java.util.Collections.unmodifiableList`, `java.util.function.Function.andThen`, `java.util.stream.Stream.toList` và `java.lang.Math.addExact/multiplyExact`; Java Language Specification về records, final fields và lambda; tài liệu Java về immutable objects và safe publication.
