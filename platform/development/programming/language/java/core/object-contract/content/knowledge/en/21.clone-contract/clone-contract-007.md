# Quy ước bản sao khác tham chiếu, cùng lớp và thường cùng giá trị trong Java

Khi nói một object được **clone** trong Java, ta thường mong muốn một **đối tượng mới** có cùng kiểu runtime, mang dữ liệu ban đầu tương ứng với object gốc. Hợp đồng `Object.clone()` mô tả ba quy ước nổi bật:

~~~java
x.clone() != x
x.clone().getClass() == x.getClass()
x.clone().equals(x)
~~~

Ba dòng trên là các **biểu thức minh họa quy ước**, chỉ có thể gọi trực tiếp nếu phương thức `clone()` đã được lớp cung cấp ở phạm vi truy cập phù hợp. Chúng **không phải ba bảo đảm tuyệt đối của mọi phương thức mang tên `clone`**. JavaDoc của `Object.clone()` nêu đây là những điều nên đúng *theo quy ước*, và có thể có ngoại lệ, nhất là biểu thức thứ ba.

Vì thế cần phân biệt: **sao chép object** khác với **sao chép toàn bộ đồ thị object được tham chiếu**, còn **cùng dữ liệu** không luôn đồng nghĩa `equals() == true`.

## 1. Ba quy ước có ý nghĩa gì?

| Quy ước | Ý nghĩa | Giới hạn cần nhớ |
|---|---|---|
| `clone != original` | Clone thường là **instance mới**, khác tham chiếu với object gốc | Một phương thức clone tự viết có thể làm sai quy ước nếu trả chính `this` |
| `clone.getClass() == original.getClass()` | Bản sao thường có **đúng cùng lớp runtime** | Đúng với đường sao chép thông thường qua `super.clone()`; override tự chế có thể trả lớp khác |
| `clone.equals(original)` | Bản sao thường bằng bản gốc **theo định nghĩa equality của lớp** | Không bảo đảm nếu lớp không override `equals()` hoặc nếu clone cố tình đổi trường dùng để so sánh |

Ví dụ, nếu lớp `Customer` có `id = 7`, bản clone cũng có `id = 7` và lớp định nghĩa `equals()` theo `id`, thì `customer.clone().equals(customer)` thường là `true`. Nếu cùng lớp đó thừa hưởng `Object.equals()` theo **identity**, hai instance khác nhau sẽ cho `false` dù có các trường trùng nhau.

Đừng gọi ba biểu thức trên là **luật kiểm tra bắt buộc** đối với tất cả lớp Java. Đó là **quy ước thiết kế và tiêu chí kiểm thử hữu ích** khi một API hứa cung cấp bản sao theo nghĩa thông thường.

## 2. `Object.clone()` và `Cloneable` hoạt động như thế nào?

`Object` khai báo phương thức **`protected Object clone() throws CloneNotSupportedException`**. Vì là `protected`, mã bên ngoài không thể tùy ý viết `someObject.clone()` nếu lớp không công khai phương thức phù hợp.

`java.lang.Cloneable` là một **marker interface**: nó **không khai báo phương thức `clone()`**. Khi gọi cơ chế `Object.clone()` trên instance của lớp không triển khai `Cloneable` (và không phải mảng), cơ chế mặc định ném `CloneNotSupportedException`. Việc viết `implements Cloneable` một mình **không tự tạo một phương thức `public clone()`** cho người dùng bên ngoài.

Mẫu triển khai phổ biến:

~~~java
final class Item implements Cloneable {
    private final int id;

    Item(int id) {
        this.id = id;
    }

    @Override
    public Item clone() {
        try {
            return (Item) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
~~~

Đây là khai báo lớp có thể biên dịch, không có `main`. Vì `Item` là `final` và triển khai `Cloneable`, lệnh `super.clone()` theo thiết kế này không phát sinh `CloneNotSupportedException`; bọc lỗi thành `AssertionError` là một lựa chọn thể hiện bất biến đó. Lớp dùng **kiểu trả về hiệp biến** (`Item` thay vì `Object`), đồng thời mở rộng mức truy cập lên `public`.

Cơ chế `super.clone()` tạo một object mới với các trường được sao chép từ object hiện tại; nó **không gọi constructor của lớp được clone** như cách `new Item(...)` thường làm. Tuy nhiên, gọi `super.clone()` cũng **không tự sao chép sâu** các object nằm trong trường tham chiếu.

## 3. Khác tham chiếu: bản clone là object mới

Với một triển khai tuân quy ước, hai biến có thể chứa thông tin giống nhau nhưng không trỏ cùng một instance:

~~~java
Item original = new Item(7);
Item copied = original.clone();

System.out.println(original == copied); // false
System.out.println(original != copied); // true
System.out.println(original.getClass() == copied.getClass()); // true
~~~

Đây là snippet sử dụng lớp `Item` ở mục trên và có thể đặt trong `main`. `==` với tham chiếu kiểm tra **identity**, không kiểm tra dữ liệu. Nếu hai biến cùng trỏ một instance, thay đổi trạng thái qua biến này tác động lên cùng object mà biến kia nhìn thấy. Nếu chúng khác instance, việc gán lại trường trực tiếp của bản này không tự thay đổi trường trực tiếp của bản kia.

Nhưng cần phân biệt **hai object gốc/clone khác nhau** với **các object con được chúng tham chiếu**: cả bản gốc và clone vẫn có thể cùng giữ tham chiếu đến một `List`, một array hoặc một object mutable. Đó là sao chép nông (*shallow copy*), phân tích ở phần dưới.

Một override sai có thể viết `return this;` và làm `clone != original` thất bại. Trình biên dịch Java không tự chặn kiểu triển khai đó; trách nhiệm bảo vệ hợp đồng thuộc người viết API.

## 4. Cùng lớp runtime: `getClass()`, không phải tên kiểu biến

Với `Object.clone()` thông thường, object được tạo có **cùng lớp runtime** với object nhận lời gọi. Nếu một biến được khai báo kiểu lớp cha nhưng trỏ tới instance lớp con, việc clone qua phương thức kế thừa có thể trả một object với lớp runtime **của lớp con**.

~~~java
Object a = new Item(9);
Item b = ((Item) a).clone();

System.out.println(a.getClass() == b.getClass()); // true
~~~

Ở ví dụ này biến `a` được khai báo `Object`, nhưng instance thực tế là `Item`. Quy ước cùng lớp xét `getClass()` của **object runtime**, không xét tên kiểu khai báo của biến, cũng không chỉ dùng `instanceof`: `instanceof` chấp nhận cả lớp con, còn phép so `getClass() == getClass()` yêu cầu đúng lớp runtime.

Khi lớp có kế thừa, `super.clone()` thường bảo toàn kiểu runtime vì clone tạo một đối tượng mới cùng kiểu thực tế của receiver. Nhưng triển khai lớp con phải cẩn thận sao chép các trường mutable do nó bổ sung; chỉ dựa vào `super.clone()` có thể để lại tham chiếu dùng chung.

Một phương thức tự viết dưới tên `clone` nhưng tạo `new Base(...)` khi receiver là `Child` có thể phá quy ước cùng lớp. Đây là một lý do không nên giả định mọi override tuân hợp đồng chỉ từ tên phương thức.

## 5. Thường cùng giá trị: vì sao `equals()` có thể vẫn false?

Cần tách **trạng thái được sao chép** khỏi **quy tắc `equals()`**:

- Nếu lớp định nghĩa `equals()` theo các trường giá trị và clone giữ các trường tương ứng, `clone.equals(original)` thường `true`.
- Nếu lớp **không override `equals()`**, mặc định của `Object.equals()` là identity. Clone là instance mới nên `clone.equals(original)` là `false`.
- Nếu `equals()` phụ thuộc dữ liệu mà clone cố ý thay đổi (ví dụ đặt lại mã định danh), `equals()` có thể `false` ngay cả khi bản sao hợp lý cho nghiệp vụ.
- Nếu lớp định nghĩa `equals()` sai đối xứng/bắc cầu hoặc có mutable state thay đổi trong lúc so sánh, kết quả cũng khó tin cậy. Đây là vấn đề thiết kế equality, không chỉ là vấn đề clone.

Ví dụ một lớp có clone nhưng vẫn dùng equality identity:

~~~java
final class IdentityItem implements Cloneable {
    int value;

    IdentityItem(int value) {
        this.value = value;
    }

    @Override
    public IdentityItem clone() {
        try {
            return (IdentityItem) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
~~~

Với hai biến `IdentityItem a = new IdentityItem(5);` và `IdentityItem b = a.clone();`, ta có `a != b` là `true`, `a.value == b.value` là `true`, nhưng `a.equals(b)` là `false`. Lớp này **không vi phạm quy tắc bắt buộc của `equals()`**; nó chỉ không đạt quy ước clone “thường equals” vì equality mặc định là identity.

Nếu muốn một **value object**, hãy định nghĩa `equals()` cùng `hashCode()` trên trường giá trị ổn định; khi dùng làm khóa trong `HashSet`/`HashMap`, tránh thay đổi trường tham gia equality/hash sau khi thêm.

## 6. Sao chép nông và sao chép sâu: ý nghĩa thực tế của “bản sao”

`super.clone()` thực hiện sao chép trường theo cơ chế mặc định (*field-by-field copy*). Với trường primitive như `int`, giá trị được sao chép. Với trường tham chiếu như `int[] scores`, **giá trị tham chiếu** được sao chép: object gốc và clone có thể trỏ cùng một array.

~~~text
Trước clone:
Original ----> scores [10, 20]

Sau super.clone() (shallow):
Original ----> scores [10, 20]
Clone    -----^

Sau copy thêm scores.clone() (tách array):
Original ----> scores [10, 20]
Clone    ----> scores [10, 20]
~~~

Đây là sơ đồ minh họa tham chiếu; hai dòng `[10, 20]` ở sơ đồ cuối đại diện cho **hai array khác nhau**, không phải cùng một array.

Nếu muốn clone có thể sửa array độc lập, cần sao chép trường array (chẳng hạn `copy.scores = scores.clone()`). Với cấu trúc phức tạp chứa nested arrays, list, map hoặc object mutable, việc sao chép một array/list bên ngoài **chưa đủ**: các phần tử tham chiếu bên trong có thể còn dùng chung, cần xem xét độ sâu phù hợp.

Thế nào là “deep copy” còn phụ thuộc hợp đồng nghiệp vụ: object bất biến như `String` có thể dùng chung an toàn, còn dữ liệu mutable thường cần được sao chép hoặc thay bằng mô hình bất biến. Không sao chép toàn bộ object graph vô điều kiện, đặc biệt khi có vòng tham chiếu, tài nguyên hệ thống hoặc identity được chia sẻ có chủ đích.

## 7. Chương trình Java 17 chạy được, có kết quả xác định

Chương trình sau kiểm tra trực tiếp ba quy ước, so sánh shallow/deep copy, xác minh constructor không được gọi khi clone, và thử lớp thiếu `Cloneable`.

Lưu file **`CloneContractDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class CloneContractDemo {
    static final class Document implements Cloneable {
        static int constructorCalls = 0;

        String title;
        int[] pages;

        Document(String title, int[] pages) {
            constructorCalls++;
            this.title = title;
            this.pages = pages;
        }

        @Override
        public Document clone() {
            try {
                return (Document) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        Document deepCopy() {
            Document result = clone();
            result.pages = pages.clone();
            return result;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Document d)) return false;
            return Objects.equals(title, d.title)
                    && Arrays.equals(pages, d.pages);
        }

        @Override
        public int hashCode() {
            return 31 * Objects.hashCode(title)
                    + Arrays.hashCode(pages);
        }
    }

    static final class IdentityItem implements Cloneable {
        final int value;

        IdentityItem(int value) {
            this.value = value;
        }

        @Override
        public IdentityItem clone() {
            try {
                return (IdentityItem) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
        // Không override equals(): dùng identity của Object.
    }

    static final class MissingMarker {
        Object attemptClone() throws CloneNotSupportedException {
            return super.clone();
        }
    }

    public static void main(String[] args) {
        Document original = new Document("Guide", new int[]{10, 20});
        Document shallow = original.clone();
        Document deep = original.deepCopy();

        System.out.println("clone different reference: "
                + (shallow != original));
        System.out.println("clone same class: "
                + (shallow.getClass() == original.getClass()));
        System.out.println("clone equals original: "
                + shallow.equals(original));
        System.out.println("shallow shares array: "
                + (shallow.pages == original.pages));
        System.out.println("deep different reference: "
                + (deep != original));
        System.out.println("deep same class: "
                + (deep.getClass() == original.getClass()));
        System.out.println("deep equals original: "
                + deep.equals(original));
        System.out.println("deep separate array: "
                + (deep.pages != original.pages));
        System.out.println("constructor calls: "
                + Document.constructorCalls);

        original.pages[0] = 99;
        System.out.println("original pages: "
                + Arrays.toString(original.pages));
        System.out.println("shallow pages: "
                + Arrays.toString(shallow.pages));
        System.out.println("deep pages: "
                + Arrays.toString(deep.pages));
        System.out.println("shallow still equals: "
                + original.equals(shallow));
        System.out.println("deep now equals original: "
                + original.equals(deep));

        IdentityItem identity = new IdentityItem(7);
        IdentityItem identityCopy = identity.clone();
        System.out.println("identity copy different: "
                + (identity != identityCopy));
        System.out.println("identity same field: "
                + (identity.value == identityCopy.value));
        System.out.println("identity equals: "
                + identity.equals(identityCopy));

        int[] array = {1, 2};
        int[] arrayCopy = array.clone();
        System.out.println("array clone different: "
                + (array != arrayCopy));
        System.out.println("array clone same class: "
                + (array.getClass() == arrayCopy.getClass()));
        System.out.println("array content equal: "
                + Arrays.equals(array, arrayCopy));

        try {
            new MissingMarker().attemptClone();
            System.out.println("missing marker: unexpected success");
        } catch (CloneNotSupportedException expected) {
            System.out.println("missing marker: CloneNotSupportedException");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac CloneContractDemo.java
java CloneContractDemo
~~~

Đầu ra:

~~~text
clone different reference: true
clone same class: true
clone equals original: true
shallow shares array: true
deep different reference: true
deep same class: true
deep equals original: true
deep separate array: true
constructor calls: 1
original pages: [99, 20]
shallow pages: [99, 20]
deep pages: [10, 20]
shallow still equals: true
deep now equals original: false
identity copy different: true
identity same field: true
identity equals: false
array clone different: true
array clone same class: true
array content equal: true
missing marker: CloneNotSupportedException
~~~

**Phân tích kết quả:**

1. `Document.clone()` tạo instance mới (`!=`) cùng runtime class (`getClass() ==`). Khi chưa thay đổi dữ liệu, bản clone bằng bản gốc vì `Document.equals()` được định nghĩa theo `title` và nội dung array.
2. `shallow.pages == original.pages` là `true`: hai Document khác nhau nhưng **cùng tham chiếu tới một array**. Chỉnh phần tử trong array ở bản gốc làm bản shallow nhìn thấy cùng thay đổi.
3. `deepCopy()` tạo clone trước rồi tách `pages` bằng `pages.clone()`; hai array khác nhau, ban đầu có cùng nội dung. Sau khi sửa array của bản gốc, bản deep giữ dữ liệu cũ và `equals` so với bản gốc trở thành `false`.
4. Bộ đếm constructor là 1 dù đã tạo thêm hai Document qua clone/deepCopy: `Object.clone()` không gọi constructor `Document`.
5. `IdentityItem` chứng minh **cùng trường không đồng nghĩa `equals == true`** khi dùng triển khai `Object.equals()` mặc định.
6. Array có `clone()` riêng, kết quả khác tham chiếu nhưng cùng runtime array class; với mảng primitive, các phần tử primitive được sao chép độc lập.
7. `MissingMarker` cho thấy phương thức `Object.clone()` ném `CloneNotSupportedException` khi lớp không implements `Cloneable`; ngoại lệ được kiểm tra thay vì để chương trình dừng.

**Giới hạn ví dụ:** `deepCopy()` chỉ sao chép sâu một tầng array primitive, vì mô hình `Document` ở đây chỉ có `String` (bất biến) và `int[]`. Với nested object mutable, cần chiến lược rõ ràng cho từng thành phần; gọi `clone()` một lần không tự tạo deep copy tổng quát.

## 8. Kế thừa và Cloneable: vì sao dễ thiết kế sai?

Một lớp cha có `public Parent clone()` dùng `super.clone()` cho phép lớp con kế thừa phương thức đó. Khi receiver thực tế là `Child`, bản sao do `Object.clone()` tạo ra vẫn có thể là **`Child` runtime**, dù kiểu trả về khai báo là `Parent`.

Tuy vậy, kế thừa làm phát sinh hai nguy cơ:

- **Lớp con thêm trường tham chiếu mutable:** `super.clone()` chỉ sao chép giá trị tham chiếu; nếu lớp con muốn độc lập, nó phải override và sao chép phần mutable được thêm.
- **Hợp đồng equality của các lớp khác nhau:** clone có thể cùng runtime class nhưng `equals()` của lớp cha/con có lỗi hoặc không có value equality. Vì vậy quy ước `clone.equals(original)` không được lấy làm chứng minh equality đã thiết kế đúng.

Nếu một superclass không được xây dựng để hỗ trợ clone, cố override tùy tiện trong subclass có thể gây vấn đề với trạng thái nội bộ và các bất biến của constructor. Đặc biệt cần xem lớp có trường `final` trỏ đến mutable object hay không: clone nông giữ chung tham chiếu, còn thiết kế sao chép sâu với trường `final` không thể chỉ gán lại một cách tùy ý trong clone.

**`Cloneable` là marker**, không phải giao diện định nghĩa `public clone()`; mã generic nhận `Cloneable` không tự gọi được `clone()` trên tham chiếu chỉ có kiểu `Cloneable`. Đây là một hạn chế quan trọng của cơ chế clone cũ.

## 9. Array, record và các lựa chọn sao chép khác

**Array** có thể `clone()` trực tiếp. Với `int[]`, phần tử primitive được chép; với `Person[]`, bản sao là array mới nhưng mỗi phần tử ban đầu vẫn trỏ đến **cùng Person**. Không nhầm `array.clone()` với deep copy của các phần tử object.

**Record** được Java khai báo là `final`, tự có `equals()`/`hashCode()` theo component, nhưng không có một phương thức `public clone()` tự sinh để sao chép record. Với record bất biến thích hợp, thường không cần clone: có thể dùng trực tiếp cùng giá trị hoặc tạo record mới từ các component nếu cần instance khác.

Nhiều thiết kế hiện đại ưu tiên **copy constructor** hoặc **static factory** vì nêu rõ chính sách sao chép:

~~~java
final class Settings {
    private final String name;
    private final int[] flags;

    Settings(String name, int[] flags) {
        this.name = name;
        this.flags = flags.clone();
    }

    Settings(Settings other) {
        this(other.name, other.flags);
    }
}
~~~

Đây là một lớp minh họa không có `main`. Constructor nhận `Settings` tạo object mới và tạo array mới. Trong thiết kế này, cả constructor chính cũng thực hiện **defensive copy** để tránh người gọi giữ tham chiếu tới `flags` mutable. Nếu cung cấp getter trả array, cũng cần cân nhắc trả bản sao để bảo vệ bất biến.

Các lựa chọn như copy constructor/factory phù hợp khi API cần hợp đồng rõ: sao chép nông hay sâu, có giữ ID hay tạo ID mới, trường mutable nào tách, có cho sao chép qua kế thừa không.

## 10. Những lỗi thường gặp

| Lỗi hoặc giả định | Vì sao sai | Hướng xử lý |
|---|---|---|
| `implements Cloneable` là tự có `public clone()` | Interface marker không khai báo phương thức | Viết phương thức clone công khai nếu API cần |
| Gọi `super.clone()` trên object không `Cloneable` | Cơ chế Object ném `CloneNotSupportedException` | Chỉ dùng với lớp thiết kế hỗ trợ clone, hoặc dùng copy constructor |
| Clone có cùng field nên chắc `equals == true` | `Object.equals` mặc định theo identity | Đọc/định nghĩa equality đúng ngữ nghĩa |
| `clone != original` nghĩa là không chia sẻ mutable state | Sao chép nông giữ nguyên tham chiếu ở trường | Sao chép thêm phần mutable cần độc lập |
| `clone.getClass() == original.getClass()` luôn được JVM cưỡng chế | Override tự viết có thể trả kiểu khác | Duy trì hợp đồng và kiểm thử runtime class |
| Thêm trường mutable ở subclass rồi chỉ kế thừa clone của cha | Mutable object mới có thể vẫn bị chia sẻ | Review và override clone ở subclass nếu cần |
| Nghĩ clone gọi constructor | `Object.clone()` sao chép trường, không gọi constructor của lớp đó | Bảo vệ bất biến; cân nhắc copy constructor |
| Dùng clone làm cơ chế duy nhất cho deep copy phức tạp | Nested references/vòng tham chiếu cần xử lý riêng | Quy định độ sâu, dùng factory hoặc sao chép có kiểm soát |
| Dùng `equals` sai hoặc `hashCode` không khớp | Hỏng collection hash nếu dùng object làm khóa | Giữ hợp đồng equality/hash, tránh mutable key |

## 11. Cách kiểm thử hợp đồng clone

Với `x` là một object dự kiến clone được, đừng chỉ kiểm tra nội dung bề ngoài. Nên kiểm thử các lớp quan hệ sau:

1. **Instance:** `clone != original` đúng theo hợp đồng công bố?
2. **Kiểu runtime:** `clone.getClass() == original.getClass()`? Nếu thiết kế cố ý trả kiểu khác, đã ghi rõ?
3. **Giá trị ban đầu:** trường primitive, tham chiếu bất biến và phần mutable có nội dung cần bảo toàn có được sao chép đúng không?
4. **Equality:** `clone.equals(original)` có đúng theo **chính định nghĩa equals của lớp** không? Nếu không, đó là chủ đích hay lỗi?
5. **Chia sẻ trạng thái:** sau khi sửa array/list mutable ở gốc, bản sao có bị thay đổi không? Điều đó có đúng với shallow/deep contract?
6. **Kế thừa:** clone một object runtime thuộc subclass rồi xác minh kiểu thực và những trường được subclass bổ sung.
7. **Ngoại lệ/truy cập:** lớp có cho phép clone không, quyền gọi là `public` hay `protected`, có cần xử lý `CloneNotSupportedException`?
8. **Bất biến và hash:** clone hay các thay đổi sau clone có phá invariant, equality hoặc cấu trúc collection băm không?

Không dùng ba quy ước như một câu thần chú để thay cho kiểm thử hành vi. Với một API sao chép mang mục tiêu khác (ví dụ tạo đơn hàng mới với ID mới), nên đặt tên và tài liệu rõ thay vì để người dùng hiểu nhầm là clone toàn bộ ý nghĩa giá trị.

## 12. Câu hỏi tự kiểm tra

**1.** `x.clone() != x` muốn bảo đảm điều gì?  
**Đáp án:** Bản sao là instance mới, không phải chỉ một alias của object gốc. Đây là quy ước thiết kế, không phải luật tuyệt đối cho mọi override.

**2.** Nếu clone có cùng class runtime nhưng `equals()` dùng `Object.equals()` mặc định, `clone.equals(original)` thường là gì?  
**Đáp án:** `false`, vì hai instance khác nhau về identity. “Cùng dữ liệu” không mặc nhiên là value equality.

**3.** `super.clone()` có tự clone mọi object được tham chiếu trong các trường không?  
**Đáp án:** Không. Nó tạo shallow copy; các trường tham chiếu mutable có thể dùng chung object con.

**4.** Vì sao `Cloneable` chưa đủ để gọi `x.clone()` từ mã bên ngoài?  
**Đáp án:** `Cloneable` không khai báo `public clone`; `Object.clone` là `protected`. Lớp phải cung cấp API sao chép có mức truy cập phù hợp.

**5.** Có thể dùng `int[] copy = source.clone()` để có array mới độc lập không?  
**Đáp án:** Có. Mảng mới khác tham chiếu và giá trị phần tử primitive được sao chép. Với `Object[]`, các tham chiếu đến phần tử object vẫn được chia sẻ nếu không sao chép thêm.

**6.** Khi nào nên chọn copy constructor thay vì clone?  
**Đáp án:** Khi cần diễn đạt công khai quy tắc sao chép, kiểm soát trường mutable/invariant hoặc xử lý mô hình có kế thừa phức tạp.

**Ghi nhớ:** Ba đặc điểm clone **khác tham chiếu, cùng lớp runtime và thường cùng giá trị** là các **quy ước mong đợi**. Để bản sao thực sự hữu ích, phải hiểu `equals()` của lớp và mức **độc lập của trạng thái mutable**, thay vì chỉ tin vào `super.clone()`.
