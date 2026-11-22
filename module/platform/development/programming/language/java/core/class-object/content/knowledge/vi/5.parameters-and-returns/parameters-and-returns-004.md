# Giá trị trả về là dữ liệu nguyên thủy, tham chiếu hoặc `null` trong Java

Một phương thức Java có thể **trả về một giá trị nguyên thủy**, **trả về một giá trị tham chiếu** đến đối tượng hoặc **trả về `null`** khi kiểu trả về cho phép. Cách khai báo kiểu trả về và cách viết câu lệnh `return` quyết định người gọi nhận được gì, có thể thao tác tiếp như thế nào và rủi ro nào phát sinh.

Ví dụ ba phương thức:

~~~java
class Sample {
    int count() {
        return 12;
    }

    String title() {
        return "Java";
    }

    String missingTitle() {
        return null;
    }
}
~~~

Đây là **đoạn khai báo minh họa**, chưa có phương thức `main` để chạy độc lập:

- `count()` trả **giá trị `int` là 12**; người gọi có thể lưu giá trị đó vào biến tương thích.
- `title()` trả **tham chiếu `String`**, trỏ đến đối tượng biểu diễn chuỗi `"Java"`.
- `missingTitle()` trả **tham chiếu null**, biểu thị hiện tại không có đối tượng `String` để sử dụng.

Java **truyền tham số theo giá trị và trả kết quả theo giá trị**: nếu kết quả có kiểu nguyên thủy, giá trị nguyên thủy được truyền về; nếu kết quả có kiểu tham chiếu, **giá trị tham chiếu** được truyền về, chứ Java không tự tạo bản sao sâu của đối tượng. Đây là ý chính xuyên suốt bài học.

## 1. Kiểu trả về nằm ở đâu trong khai báo phương thức?

Một khai báo method điển hình:

~~~java
class Product {
    private final String name;
    private final long price;

    Product(String name, long price) {
        this.name = name;
        this.price = price;
    }

    long getPrice() {       // Kiểu trả về: long
        return price;
    }

    String getName() {      // Kiểu trả về: String
        return name;
    }

    void printName() {      // Không có giá trị trả về
        System.out.println(name);
    }
}
~~~

Đây là đoạn khai báo, không phải chương trình độc lập. Trong `long getPrice()`, `long` đứng trước tên phương thức là **declared return type**; trong `String getName()`, `String` là kiểu tham chiếu. Keyword `return` kết thúc thực thi method hiện tại, đồng thời mang một biểu thức kết quả khi method yêu cầu giá trị.

Phân biệt ba hình thức:

~~~java
int doubleNumber(int n) {
    return n * 2;              // trả một int
}

String findName(boolean found) {
    if (found) {
        return "Lan";          // trả một tham chiếu String
    }
    return null;               // cùng kiểu trả về String, nhưng không có đối tượng
}

void notifyDone() {
    System.out.println("Done");
    return;                    // hợp lệ: kết thúc void method, không có biểu thức
}
~~~

Đây là các **mảnh khai báo method** cần đặt trong một class. Với method có kết quả, compiler kiểm tra mọi đường thực thi có thể kết thúc bình thường phải trả giá trị phù hợp hoặc bị loại trừ bởi exception/luồng điều khiển hợp lệ. Không thể chỉ bỏ trống `return` nếu method khai báo trả `int` hoặc `String`. Method `void` không trả giá trị; có thể không viết `return;` và kết thúc ở cuối thân method.

**Constructor** không phải method có kiểu trả về: constructor có tên trùng class, không khai báo `int`, `String` hay `void`. Câu lệnh `return;` trong constructor có thể dùng để kết thúc sớm khi hợp lệ, nhưng constructor **không trả biểu thức kết quả**; biểu thức `new Product(...)` mới tạo ra tham chiếu đến đối tượng.

## 2. Tổng quan kết quả: primitive, reference, null và void

| Kiểu khai báo của method | Ví dụ | Người gọi nhận được |
| --- | --- | --- |
| Primitive `int` | `int size() { return 3; }` | Giá trị `int` 3 |
| Primitive `boolean` | `boolean isReady() { return true; }` | Giá trị `boolean` true |
| Primitive `double` | `double rate() { return 0.5; }` | Giá trị `double` 0.5 |
| Reference `String` | `String label() { return "A"; }` | Giá trị tham chiếu đến một `String` |
| Reference `int[]` | `int[] numbers() { return new int[]{1,2}; }` | Giá trị tham chiếu đến mảng |
| Reference `Customer` | `Customer find() { return null; }` | Giá trị null thuộc ngữ cảnh kiểu `Customer` |
| Reference `Integer` | `Integer score() { return 10; }` | Tham chiếu đến wrapper `Integer` qua boxing |
| `void` | `void clear() { return; }` | **Không có giá trị kết quả** |

Các dòng trong bảng là những method ngắn để minh họa, không phải một chương trình đầy đủ. Java chỉ có **tám kiểu primitive**: `byte`, `short`, `int`, `long`, `float`, `double`, `char` và `boolean`. Mọi kiểu class, interface, array và các kiểu tham chiếu tương ứng thuộc nhóm reference.

**`null` không phải kiểu khai báo return của method**; không thể viết `null find()`. Nó là giá trị đặc biệt có thể dùng cho các kiểu tham chiếu thích hợp: `String`, `Integer`, `List<String>`, mảng, record, interface, v.v. Bên cạnh đó, Java có **null type** trong mô tả kiểu của ngôn ngữ, nhưng bạn không khai báo `null` như một return type thông thường.

## 3. Trả về primitive: người gọi nhận một giá trị độc lập

Ví dụ:

~~~java
class Battery {
    private int percentage = 75;

    int getPercentage() {
        return percentage;
    }

    void drain(int amount) {
        percentage -= amount;
    }
}
~~~

Đây là đoạn minh họa. Khi thực hiện:

~~~java
Battery battery = new Battery();
int snapshot = battery.getPercentage();  // snapshot = 75
battery.drain(10);

// snapshot vẫn là 75; battery.getPercentage() bây giờ là 65
~~~

`getPercentage()` trả **giá trị hiện tại** của field `percentage`; biến `snapshot` giữ bản sao giá trị `75`. Một command thay đổi field về sau không tự cập nhật biến `snapshot`.

Với primitive, không có đối tượng “phía sau kết quả” để caller sửa qua kết quả. Người gọi có thể làm phép tính với `snapshot`, nhưng việc gán `snapshot = 100` không ghi trở lại `battery.percentage`.

### 3.1. Biểu thức `return` phải tương thích kiểu khai báo

Java cho phép một số chuyển đổi hợp lệ ở ngữ cảnh trả kết quả theo quy tắc ngôn ngữ. Chẳng hạn một `int` có thể được **widening** thành `long`:

~~~java
long count() {
    int local = 42;
    return local;             // int -> long: hợp lệ
}
~~~

Nhưng phép thu hẹp không được tự chấp nhận tùy ý:

~~~java
int rounded() {
    double value = 2.7;
    // return value;          // Lỗi biên dịch: double -> int không tự thu hẹp
    return (int) value;       // Hợp lệ: trả 2 do ép kiểu tường minh
}
~~~

Các ví dụ là method fragment. Với ép `double` sang `int`, phần thập phân được bỏ theo quy tắc chuyển đổi của Java, không phải làm tròn theo cách người dùng thường hiểu. Vì vậy tên `rounded()` trong ví dụ chỉ nhấn mạnh lỗi thiết kế đặt tên; nếu ý định thật sự là làm tròn, hãy dùng quy tắc phù hợp như `Math.round` và chú ý kiểu kết quả.

Khi thiết kế method, nên chọn declared return type thể hiện **đúng miền giá trị**, tránh ép kiểu để che lỗi tràn số hoặc mất độ chính xác.

### 3.2. Primitive không bao giờ trả trực tiếp `null`

~~~java
int findQuantity() {
    // return null;          // Lỗi biên dịch
    return 0;
}
~~~

`0` là một giá trị thực của kiểu `int`, không đồng nghĩa chắc chắn với “không tìm thấy”. Nếu miền nghiệp vụ cần phân biệt “không có số lượng” và “số lượng bằng 0”, đừng chọn sentinel tùy tiện mà không định nghĩa hợp đồng. Có thể sử dụng `OptionalInt`, wrapper `Integer` có thể null, một kiểu kết quả riêng hoặc ném exception khi thiếu dữ liệu là lỗi, tùy API.

## 4. Trả về reference: chia sẻ tham chiếu, không tự sao chép object

Method có return type là class, interface, array hoặc kiểu tham chiếu khác sẽ trả một **giá trị tham chiếu**. Giá trị đó có thể trỏ tới:

- Một object đã tồn tại và được field của class giữ.
- Một object vừa tạo bằng `new`.
- Một object được lấy từ cache, collection hoặc tham số.
- Chính object đang nhận method thông qua `this`, nếu kiểu trả về phù hợp.
- Không có object nào, tức `null`.

Ví dụ:

~~~java
class City {
    String name;

    City(String name) {
        this.name = name;
    }
}

class TravelProfile {
    private final City home = new City("Huế");

    City getHome() {
        return home;          // trả tham chiếu đến object nội bộ
    }

    City copyHome() {
        return new City(home.name); // tạo object mới
    }
}
~~~

Hai method có **cùng kiểu trả về `City`**, nhưng hợp đồng sở hữu khác nhau. `getHome()` làm lộ đối tượng mutable nội bộ; `copyHome()` tạo một đối tượng `City` độc lập (với ví dụ này field String immutable nên việc sao chép chuỗi không gây aliasing mutable).

Nếu caller gọi:

~~~java
TravelProfile profile = new TravelProfile();
City shared = profile.getHome();
shared.name = "Đà Nẵng";
~~~

thì object `City` nằm trong `profile` cũng đổi tên thành `"Đà Nẵng"`, vì `shared` là **tham chiếu đến đúng object nội bộ**. Phần này là code fragment cần đặt trong một method.

Ngược lại:

~~~java
City independent = profile.copyHome();
independent.name = "Hà Nội";
// Không sửa object City nội bộ của profile qua independent
~~~

Ghi nhớ: `return home;` **không clone**, không “đóng băng” object và không truyền quyền sở hữu riêng biệt cho người gọi. Nếu object mutable, caller có thể thay đổi trạng thái của object mà cả hai bên cùng tham chiếu đến, tùy quy tắc truy cập.

### 4.1. Trả về tham chiếu giống tham số nhận vào

~~~java
class TextOps {
    static StringBuilder appendBang(StringBuilder text) {
        text.append("!");
        return text;
    }
}
~~~

Đây là đoạn minh họa. `appendBang` vừa sửa object nhận vào vừa trả **cùng tham chiếu**. Một method có reference return không mặc định là “query” hay không có side effect; ý định vẫn phải đọc từ hợp đồng.

Java cũng truyền tham số tham chiếu **theo giá trị**. Việc method gán lại tham số, ví dụ `text = new StringBuilder()`, không làm biến của caller trỏ sang đối tượng mới; nhưng gọi `text.append(...)` có thể sửa object đang được hai bên tham chiếu.

### 4.2. String là reference nhưng immutable

~~~java
class Message {
    private String text = "Xin chào";

    String getText() {
        return text;
    }
}
~~~

`getText()` trả tham chiếu `String`, nhưng `String` là immutable: caller không thể sửa trực tiếp nội dung object String được trả về. Gọi `returnedText.toUpperCase()` tạo ra một chuỗi kết quả (hoặc có thể dùng lại object nếu phù hợp) mà không sửa nội dung String ban đầu.

**Không suy luận “reference = có thể sửa được”.** Mutability phụ thuộc thiết kế class/kiểu dữ liệu. `String`, nhiều record chứa chỉ thành phần immutable và các immutable value object có thể trả qua reference mà không làm lộ mutable state; mảng, `ArrayList`, `StringBuilder` thường đòi cân nhắc kỹ hơn.

## 5. `null` là một kết quả hợp lệ của reference method

Ví dụ:

~~~java
class Directory {
    String findDisplayName(int id) {
        if (id == 7) {
            return "Lan";
        }
        return null;
    }
}
~~~

Đây là một API đơn giản dùng `null` biểu thị “không tìm thấy”. Phương thức **khai báo trả `String`**; nó không cần khai báo thêm một kiểu `null` để trả null.

Code gọi nên kiểm tra trước khi thao tác với đối tượng:

~~~java
Directory directory = new Directory();

String name = directory.findDisplayName(9);
if (name != null) {
    System.out.println(name.length());
} else {
    System.out.println("Không tìm thấy");
}
~~~

Nếu bỏ kiểm tra rồi chạy `name.length()` khi `name == null`, chương trình sẽ ném `NullPointerException`. Các thao tác **truy cập method/field hoặc mảng qua null** là những nguồn lỗi phổ biến.

Không phải mọi thao tác với biến null đều ném exception:

- `name == null` hợp lệ và trả boolean.
- `System.out.println(name)` in chữ `null` khi `name` là null nhờ overload phù hợp của phương thức in.
- `name instanceof String` trả `false` nếu `name` là null.
- `Objects.equals(name, "Lan")` trả `false` an toàn khi name là null.
- `name.length()` ném `NullPointerException` khi name là null.

### 5.1. Dữ liệu thiếu, rỗng và mặc định là các khái niệm khác nhau

Với `String`, các trường hợp sau có ý nghĩa khác nhau:

| Giá trị trả về | Ý nghĩa có thể có |
| --- | --- |
| `null` | Không có đối tượng/kết quả (theo hợp đồng API) |
| `""` | Có một String nhưng độ dài bằng 0 |
| `" "` | Có String chứa một dấu cách |
| `"Lan"` | Có String nội dung “Lan” |

Không tự ý đổi mọi `null` thành `""` nếu dữ liệu thiếu và dữ liệu rỗng mang nghĩa khác nhau. Tương tự, với collection, trả `Collections.emptyList()` hoặc `List.of()` thể hiện “có kết quả nhưng danh sách rỗng” trong nhiều API; trả `null` có thể thể hiện “không có kết quả”, nhưng cũng gây gánh nặng kiểm tra cho caller. Chọn một hợp đồng và áp dụng nhất quán.

### 5.2. Không có khai báo nullability bắt buộc trong kiểu Java thông thường

Một method khai báo `String getName()` **vẫn có thể trả `null`** mà compiler Java chuẩn chấp nhận. Java 17 không phân biệt bằng cú pháp kiểu thông thường `String` “không thể null” và “có thể null”. Một số dự án dùng annotation như `@Nullable` hoặc `@NonNull` cùng static analyzer hoặc quy ước; hiệu lực phụ thuộc thư viện và công cụ, không phải bất cứ annotation nào cũng tự động chặn null ở runtime.

Nếu API đảm bảo kết quả khác null, hãy kiểm soát điều đó bằng validation và thực thi nhất quán; nếu kết quả có thể thiếu, ghi rõ trong tài liệu hoặc biểu diễn bằng một kiểu phù hợp.

## 6. Wrapper type: khi một giá trị số cũng có thể là `null`

Các class như `Integer`, `Long`, `Double`, `Boolean` là **reference types** tương ứng với các primitive. Ví dụ:

~~~java
class QuizResult {
    Integer getScore(boolean submitted) {
        if (!submitted) {
            return null;       // chưa nộp bài
        }
        return 0;              // boxing int 0 -> Integer
    }
}
~~~

`getScore(false)` trả null; `getScore(true)` trả một `Integer` chứa giá trị 0. Điều này giúp phân biệt “chưa có điểm” với “điểm thật sự bằng 0”.

Java có **autoboxing** và **unboxing**:

~~~java
Integer boxed = 10; // boxing từ int sang Integer
int unboxed = boxed; // unboxing từ Integer sang int
~~~

Nếu biến `boxed` là null, phép unboxing gây `NullPointerException`:

~~~java
Integer missing = null;
// int count = missing; // Biên dịch được nếu bỏ comment, nhưng NPE khi chạy
~~~

Sự cố cũng có thể xảy ra **ngay trong câu lệnh return**:

~~~java
int score(Integer result) {
    return result; // compiler unbox Integer -> int; NPE nếu result == null
}
~~~

Đây là các mảnh code minh họa, cần nằm trong class. Hãy phân biệt lỗi:

- `int get() { return null; }`: **lỗi biên dịch**, vì null không chuyển trực tiếp thành primitive.
- `int get(Integer boxed) { return boxed; }`: **biên dịch được**, nhưng **có thể lỗi runtime** khi unboxing null.

Một method trả `Integer` không có nghĩa nó luôn tạo object mới mỗi lần; JVM có thể cache các wrapper với một số giá trị theo quy định và triển khai. Đừng dùng `==` để so sánh ý nghĩa số của hai `Integer`. Nếu cả hai khác null và bạn cần so sánh số, có thể dùng `intValue()` hoặc `equals` theo hợp đồng; nếu có thể null, `Objects.equals(a, b)` giúp so sánh an toàn.

## 7. Ví dụ chạy được: ba dạng kết quả, aliasing và null

Chương trình sau minh họa đầy đủ **primitive result**, **reference result được chia sẻ**, **reference result được sao chép**, **`null` và wrapper**.

Lưu thành tệp **`ReturnKindsDemo.java`**:

~~~java
public class ReturnKindsDemo {
    static final class Inventory {
        private int stock = 10;
        private final int[] bins = {2, 4};
        private final String name = "Kho A";

        int getStock() {            // primitive
            return stock;
        }

        String getName() {          // immutable reference
            return name;
        }

        int[] getLiveBins() {       // trả cùng mảng nội bộ
            return bins;
        }

        int[] getBinsCopy() {       // trả mảng mới
            return bins.clone();
        }

        String findLabel(boolean found) {
            return found ? "Đã tìm thấy" : null;
        }

        Integer findStock(boolean found) {
            if (!found) {
                return null;
            }
            return stock;          // int được boxing thành Integer
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();

        int copiedStock = inventory.getStock();
        copiedStock = 99;
        System.out.println("Copied stock = " + copiedStock);
        System.out.println("Real stock = " + inventory.getStock());

        int[] live = inventory.getLiveBins();
        live[0] = 8;
        System.out.println("Live first = " + inventory.getLiveBins()[0]);

        int[] copy = inventory.getBinsCopy();
        copy[0] = 77;
        System.out.println("After copy edit = " + inventory.getLiveBins()[0]);

        System.out.println("Name = " + inventory.getName());
        System.out.println("Missing label = "
                + (inventory.findLabel(false) == null));

        Integer missingStock = inventory.findStock(false);
        Integer presentStock = inventory.findStock(true);
        System.out.println("Missing stock = " + (missingStock == null));
        System.out.println("Present stock = " + presentStock);
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 ReturnKindsDemo.java
java ReturnKindsDemo
~~~

**Stdout chính xác:**

~~~text
Copied stock = 99
Real stock = 10
Live first = 8
After copy edit = 8
Name = Kho A
Missing label = true
Missing stock = true
Present stock = 10
~~~

**Phân tích từng kết quả:**

1. `getStock()` trả primitive `int` 10. Gán `copiedStock = 99` chỉ sửa biến của caller, nên `getStock()` vẫn trả 10.
2. `getLiveBins()` trả tham chiếu đến **mảng bên trong Inventory**. `live[0] = 8` sửa mảng gốc, nên gọi lại `getLiveBins()[0]` thấy 8.
3. `getBinsCopy()` tạo một mảng `int[]` khác bằng `clone()`. Sửa `copy[0] = 77` không làm thay đổi mảng gốc: kết quả in vẫn 8.
4. `getName()` trả tham chiếu `String` "Kho A". String immutable; chỉ riêng việc trả tham chiếu không gây rủi ro sửa trực tiếp nội dung String.
5. `findLabel(false)` trả `null`; phép so sánh `== null` trả true và không dereference.
6. `findStock(false)` trả `null` dạng reference `Integer`; `findStock(true)` boxing `int` 10 thành `Integer`. Cả hai trường hợp đều khớp declared return type.

Đây là cách tự quan sát những ngữ nghĩa khác nhau mà **không cần đoán “object có được copy hay không”**: kiểm tra biểu thức `return` có thực hiện `new`/`clone` hay chỉ trả reference cũ. Nếu kiểu là mutable và không có copy, phải chủ động đánh giá aliasing.

## 8. Trả về mảng/collection: bảo vệ dữ liệu nội bộ

Một getter đôi khi trông như chỉ đọc nhưng gây lộ trạng thái mutable:

~~~java
import java.util.ArrayList;
import java.util.List;

class BadLibrary {
    private final List<String> books = new ArrayList<>();

    List<String> getBooks() {
        return books; // caller có thể books.clear(), books.add(...)
    }
}
~~~

Đây là đoạn khai báo minh họa. Người gọi có thể viết `library.getBooks().clear()`, bypass các method có kiểm tra invariant. Mức truy cập `private` của field không đủ bảo vệ nếu method trả trực tiếp tham chiếu tới collection.

Cách trả kết quả có bảo vệ:

~~~java
import java.util.ArrayList;
import java.util.List;

class Library {
    private final List<String> books = new ArrayList<>();

    List<String> getBooks() {
        return List.copyOf(books);
    }

    void addBook(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tên sách rỗng");
        }
        books.add(title);
    }
}
~~~

Với phần tử `String` immutable, `List.copyOf(books)` cung cấp một danh sách không sửa được qua API và phản ánh nội dung tại thời điểm tạo kết quả, khác với getter trả thẳng `books`. Vì danh sách nguồn `books` ở đây mutable, kết quả không chia sẻ khả năng thay đổi cấu trúc với danh sách nguồn. `List.copyOf` không chấp nhận phần tử null; nếu nghiệp vụ cho phép null trong list, phải thiết kế cơ chế khác cho phù hợp.

**Chú ý shallow copy:** nếu `books` là `List<Book>` và `Book` mutable, bản sao cấu trúc danh sách vẫn chứa tham chiếu tới **cùng các `Book`**. Người gọi có thể sửa nội dung phần tử khi API của `Book` cho phép. Tùy hợp đồng, cần trả DTO/record bất biến hoặc bản sao sâu phù hợp.

### 8.1. Snapshot, view và direct reference khác nhau

| Cách trả về | Tính chất |
| --- | --- |
| `return mutableList;` | Trả trực tiếp object nội bộ; caller có thể mutate nếu API cho phép |
| `return Collections.unmodifiableList(mutableList);` | View không cho sửa qua view, nhưng có thể phản ánh thay đổi của danh sách gốc |
| `return List.copyOf(mutableList);` | Kết quả không sửa được và không phản ánh cập nhật cấu trúc sau đó của nguồn mutable |
| `return new ArrayList<>(mutableList);` | Mảng/danh sách mới nhưng **mutable**, copy nông các phần tử |
| `return array.clone();` | Mảng mới, sao chép nông; với mảng primitive, giá trị phần tử độc lập |

Chọn kết quả theo hai câu hỏi: caller có được quyền sửa kết quả không, và kết quả có cần **theo dõi live state** hay phải là **ảnh chụp trạng thái** tại thời điểm gọi? Tên method và tài liệu nên làm rõ.

## 9. Dùng `Optional` khi kết quả có thể không tồn tại

Java cung cấp `java.util.Optional<T>` như một kiểu **giá trị trả về** biểu diễn “có kết quả” hoặc “không có kết quả” mà không cần để caller tự dereference một `null`.

~~~java
import java.util.Optional;

class UserDirectory {
    Optional<String> findName(int id) {
        if (id == 7) {
            return Optional.of("Lan");
        }
        return Optional.empty();
    }
}
~~~

Đây là đoạn khai báo minh họa. Cách sử dụng:

~~~java
Optional<String> result = directory.findName(7);
String name = result.orElse("Khách");
System.out.println(name);
~~~

Phần này cần có biến `directory` tham chiếu `UserDirectory` và nằm trong method. Khi `id == 7`, kết quả là `"Lan"`; nếu không tìm thấy, `orElse("Khách")` trả fallback `"Khách"`.

Những phương thức thường dùng:

- `Optional.of(value)`: yêu cầu value khác null, ném `NullPointerException` nếu null.
- `Optional.ofNullable(value)`: trả `Optional.empty()` khi value null, còn lại chứa giá trị.
- `Optional.empty()`: biểu diễn không có kết quả.
- `optional.isPresent()` hoặc `optional.isEmpty()`: kiểm tra có/không có giá trị.
- `optional.orElse(defaultValue)`: trả giá trị nếu có, hoặc fallback đã được đánh giá.
- `optional.orElseGet(supplier)`: gọi supplier để tạo fallback **chỉ khi cần**.
- `optional.orElseThrow()`: ném `NoSuchElementException` nếu rỗng, hoặc `orElseThrow(supplier)` cho lỗi tùy chọn.
- `optional.map(fn)`: biến đổi giá trị đang có mà giữ trạng thái empty khi không có.

**Không trả `null` từ method khai báo `Optional<T>`**: khi thiếu dữ liệu, hãy trả `Optional.empty()`. Nếu trả null cho `Optional`, bạn lại buộc caller kiểm tra null bên ngoài Optional và làm mất ý nghĩa hợp đồng.

`Optional<T>` là reference type với một **đối tượng Optional** chứa tham chiếu hoặc trạng thái empty; không thể dùng primitive làm type argument trực tiếp như `Optional<int>`. Nếu cần một giá trị `int` tùy chọn, cân nhắc `OptionalInt`.

### 9.1. Ví dụ hoàn chỉnh với Optional và OptionalInt

Lưu thành tệp **`OptionalResultDemo.java`**:

~~~java
import java.util.Optional;
import java.util.OptionalInt;

public class OptionalResultDemo {
    static Optional<String> findCity(int personId) {
        return personId == 7
                ? Optional.of("Hà Nội")
                : Optional.empty();
    }

    static OptionalInt findAge(int personId) {
        return personId == 7
                ? OptionalInt.of(21)
                : OptionalInt.empty();
    }

    public static void main(String[] args) {
        System.out.println("City = " + findCity(7).orElse("Không rõ"));
        System.out.println("Missing city = "
                + findCity(9).orElse("Không rõ"));

        System.out.println("Age = " + findAge(7).orElse(-1));
        System.out.println("Has missing age = "
                + findAge(9).isPresent());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OptionalResultDemo.java
java OptionalResultDemo
~~~

Stdout:

~~~text
City = Hà Nội
Missing city = Không rõ
Age = 21
Has missing age = false
~~~

Ở đây method có thể thiếu dữ liệu trả **Optional rỗng**, không trả null. Caller phải xác định cách xử lý trường hợp rỗng; `orElse(-1)` là fallback tại điểm gọi, **không phải giá trị tuổi mặc định do Java tự tạo**.

### 9.2. Khi nào dùng `null`, Optional hay exception?

| Tình huống | Kiểu trả về gợi ý | Lý do |
| --- | --- | --- |
| Kết quả luôn tồn tại theo invariant | `String` hoặc kiểu tương ứng, bảo đảm khác null | API đơn giản, hợp đồng rõ |
| Không tìm thấy là kết quả bình thường | `Optional<T>` hoặc `OptionalInt` | Caller xử lý hiện diện rõ ràng |
| API cũ quy định dùng null | `T` có thể trả null, tài liệu rõ | Tương thích hợp đồng hiện có |
| Thiếu giá trị là lỗi hợp đồng hoặc thao tác | Có thể ném exception phù hợp | Không trả sentinel mơ hồ |
| Có thể trả tập kết quả rỗng | `List<T>` trả collection rỗng | Dễ duyệt, không phải null-check thường xuyên |

`Optional` không phải “chữa mọi null”: nó cũng là một reference type và về mặt ngôn ngữ có thể bị gán null, dù API không nên làm như vậy. Optional có chi phí và cách sử dụng riêng, không nhất thiết phù hợp với mọi field, mọi tham số hoặc mọi định dạng serialization.

## 10. Phân biệt `null`, exception và một giá trị sentinel

Hãy xét method tìm số dư. Các phương án:

~~~java
// Phương án 1: -1 chỉ là sentinel nếu toàn bộ hợp đồng quy định -1 không hợp lệ
int findBalanceOrMinusOne(int id) {
    return id == 7 ? 100 : -1;
}

// Phương án 2: Integer cho phép phân biệt null với số 0
Integer findBalanceNullable(int id) {
    return id == 7 ? Integer.valueOf(100) : null;
}

// Phương án 3: OptionalInt làm việc thiếu giá trị thành trường hợp rõ ràng
java.util.OptionalInt findBalance(int id) {
    return id == 7
            ? java.util.OptionalInt.of(100)
            : java.util.OptionalInt.empty();
}
~~~

Đây là các method fragment có thể đặt trong class. Nếu số dư hợp lệ có thể âm, lựa chọn `-1` làm sentinel có thể gây lỗi. Một exception phù hợp khi id sai là tình huống bất thường theo hợp đồng, không nhất thiết khi “không tìm thấy” là điều dự kiến.

**Tính nhất quán quan trọng hơn lựa chọn mang tính thời trang:** nếu một API đã có hợp đồng trả null thì caller phải được hướng dẫn xử lý; nếu một dự án chuẩn hóa Optional cho tìm kiếm, hãy áp dụng nhất quán tại ranh giới phù hợp. Đừng trả `0` chỉ để tránh null nếu `0` là một giá trị nghiệp vụ thật.

## 11. Trả `this`, object mới và tham chiếu kiểu cha/interface

Giá trị trả về có thể là chính đối tượng hiện tại:

~~~java
class Builder {
    private String text = "";

    Builder append(String part) {
        text += part;
        return this;
    }

    String build() {
        return text;
    }
}
~~~

Đây là đoạn minh họa. `append` trả lại **tham chiếu `this`** để chain lời gọi; nó đồng thời thay đổi trạng thái, nên không phải query thuần. `build()` trả tham chiếu String tới kết quả hiện tại; do String immutable, caller không sửa trực tiếp nội dung đã nhận.

Một phương thức có thể khai báo return type là **interface hoặc superclass** và thực tế trả tham chiếu object thuộc implementation/subclass tương thích:

~~~java
import java.util.ArrayList;
import java.util.List;

class Selection {
    List<String> values() {
        return new ArrayList<>(List.of("A", "B"));
    }
}
~~~

`List<String>` là declared return type, còn object thực tế là một `ArrayList<String>`. Người gọi có thể sử dụng các API hiển thị qua kiểu `List`. Việc method trả implementation object qua interface không biến object thành immutable: `ArrayList` vẫn mutable nếu caller thực hiện các thao tác được cho phép bởi interface.

**Không nhầm runtime class với declared return type.** Compiler kiểm tra biểu thức `return` tương thích với declared type; object thực tế có thể thuộc subtype.

### 11.1. Covariant return khi override

Với instance method được override, Java cho phép một subclass trả **kiểu tham chiếu cụ thể hơn** theo quy tắc return-type substitutability:

~~~java
class Animal { }

class Dog extends Animal { }

class Shelter {
    Animal adopt() {
        return new Animal();
    }
}

class DogShelter extends Shelter {
    @Override
    Dog adopt() {
        return new Dog();
    }
}
~~~

Đây là đoạn minh họa, không có `main`. `DogShelter.adopt()` trả `Dog`, tương thích kiểu con của `Animal`. Không thể tùy tiện đổi kiểu primitive khi override, chẳng hạn superclass trả `int` còn subclass trả `long`, vì widening primitive không tạo ra covariant return trong overriding.

## 12. Phương thức generic có kiểu trả về là tham số kiểu

Một method generic có thể biểu diễn kiểu kết quả qua type parameter:

~~~java
class Results {
    static <T> T first(T first, T second) {
        return first;
    }
}
~~~

Đây là đoạn khai báo. Nếu gọi `String name = Results.first("Lan", "Mai")`, caller nhận một `String`; nếu gọi `Integer number = Results.first(1, 2)`, caller nhận wrapper `Integer` theo generic type inference/boxing.

Vì **generic type argument thông thường phải là reference type**, không thể viết `List<int>` hoặc `Optional<int>`; dùng `List<Integer>`, `OptionalInt` hoặc cấu trúc phù hợp. Một method generic trả `T` có thể trả `null` nếu thân method thực hiện như vậy và hợp đồng cho phép; kiểu generic **không tự bảo đảm non-null**.

Cũng cần chú ý type erasure: nó ảnh hưởng runtime representation và một số kiểm tra kiểu, nhưng không làm thay đổi nguyên tắc “trả giá trị tham chiếu” của kết quả generic.

## 13. Lưu ý về lifecycle và kết quả trỏ đối tượng dùng chung

Một object được trả về có thể còn được tham chiếu ở nhiều nơi: field nội bộ, cache, static field, tham số của lời gọi hoặc các đối tượng khác. Vì vậy việc trả object **không chuyển quyền sở hữu độc quyền** theo mặc định.

Các tình huống:

1. **Trả một DTO/record chỉ chứa primitive và String:** phù hợp chia sẻ nếu không có thành phần mutable.
2. **Trả một `ArrayList` mutable đang dùng nội bộ:** người gọi có thể sửa danh sách nội bộ ngoài kiểm soát.
3. **Trả danh sách sao chép nông chứa object mutable:** phần tử bên trong vẫn có thể được chia sẻ.
4. **Trả một `InputStream` hoặc connection:** cần quy định rõ **ai đóng resource**; giá trị return đơn thuần không chuyển trách nhiệm đóng theo quy tắc ngôn ngữ.
5. **Trả tham chiếu đến object có thể thay đổi từ thread khác:** một lần gọi query trả cùng object không tạo snapshot atomically và không cung cấp bảo đảm thread-safety.
6. **Trả null cho kết quả “không có”:** người gọi cần nhánh xử lý hoặc một wrapper kết quả rõ ràng.

Với mutable objects, nên xác định rõ về **ownership**, khả năng thay đổi (*mutability*), số bản sao, thread-safety và vòng đời của object trả về. Đây là một phần của **hợp đồng phương thức**, không thể suy ra chỉ từ cú pháp `return`.

## 14. Trả kết quả trong bối cảnh đa luồng

Ví dụ một method:

~~~java
class Metrics {
    private int count;

    int currentCount() {
        return count;
    }

    void increment() {
        count++;
    }
}
~~~

`currentCount()` trả primitive nên caller nhận bản sao một lần đọc, nhưng khi nhiều thread gọi `increment()` và `currentCount()` mà thiếu đồng bộ, còn có vấn đề data race, visibility và lost update. **Primitive return không tự biến một field chia sẻ thành thread-safe**.

Nếu trả một mutable reference, caller có thể gặp cả việc nội dung object bị cập nhật đồng thời. Cần giải pháp theo hợp đồng: `synchronized`, lock, atomic variable, immutable snapshot xuất bản an toàn hoặc concurrent collection khi phù hợp.

Ví dụ snapshot immutable đơn giản:

~~~java
record Status(int completed, int failed) { }

class StatusHolder {
    private volatile Status current = new Status(0, 0);

    Status snapshot() {
        return current;
    }

    void replace(Status next) {
        current = java.util.Objects.requireNonNull(next);
    }
}
~~~

Đây là đoạn minh họa. `snapshot()` trả một tham chiếu đến record `Status` hiện hành, được xuất bản qua volatile field. Mỗi record chứa hai primitive component và không có mutable nested object trong ví dụ; caller đọc hai giá trị qua **cùng biến kết quả** sẽ thấy một phiên bản nhất quán. Tuy nhiên, `replace` không phải cập nhật cộng dồn atomically: hai writer cùng tính state mới từ snapshot cũ có thể ghi đè nhau. Nếu cần read-modify-write nguyên tử, dùng cơ chế đồng bộ phù hợp.

## 15. Lỗi phổ biến với kiểu trả về

| Sai lầm | Hệ quả | Cách hiểu/sửa |
| --- | --- | --- |
| `int get() { return null; }` | Lỗi biên dịch | Primitive không nhận null |
| `int get(Integer x) { return x; }` với x null | `NullPointerException` runtime | Unboxing cần giá trị non-null |
| Cho rằng `return object;` tự clone | Caller chia sẻ object cũ | Tạo copy nếu cần độc lập |
| Getter trả thẳng mảng nội bộ | Caller có thể sửa mảng | Defensive copy hoặc API chỉ đọc |
| Dùng `==` so sánh nội dung String | So sánh identity, dễ sai | `equals` / `Objects.equals` |
| Luôn trả `0` khi không tìm thấy số | Lẫn lộn dữ liệu thiếu và giá trị 0 | Optional/wrapper/result type |
| Method khai báo `Optional<T>` nhưng trả null | Phá hợp đồng Optional | Trả `Optional.empty()` |
| Nghĩ `String` là primitive | Sai hiểu biết về tham chiếu | String là class immutable |
| Nghĩ `void` trả `null` | Sai: void không trả giá trị | Không dùng void call như biểu thức có kết quả |
| Gọi `toString()` trên kết quả nullable | Có thể ném NPE | Kiểm tra null hoặc xử lý Optional |
| Dùng `new` trong method mà nghĩ caller nhận bản sao của tham số | Không suy ra được | Xem chính object nào được tạo/return |
| Trả collection copy rồi cho rằng mọi phần tử đều đã deep-copy | Object con mutable vẫn chia sẻ | Thiết kế snapshot/deep copy nếu cần |

### 15.1. Câu hỏi có vẻ đơn giản nhưng dễ nhầm

~~~java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Đây là fragment trong method. Hai `new String(...)` ở đây tạo hai đối tượng String khác nhau nhưng có nội dung bằng nhau. Nếu method trả `a` ở lần một và `b` ở lần hai, declared return type đều là String, song identity của kết quả khác nhau. Không dùng phép `==` như phép so sánh nội dung văn bản.

Một ví dụ khác:

~~~java
int[] createArray() {
    return new int[]{1, 2, 3};
}
~~~

Đây là method fragment: kiểu trả về `int[]` là **reference type**, dù phần tử là primitive `int`. Mỗi lần thực thi `new int[]{...}` tạo object mảng mới; khác với `return sharedArray;` trả tham chiếu mảng cũ.

## 16. Tự kiểm tra

**Câu 1.** Method `int answer() { return 42; }` trả về object `Integer` hay primitive `int`?

**Trả lời:** Trả primitive `int`; người gọi có thể tự boxing nếu gán kết quả vào `Integer` trong ngữ cảnh tương thích.

**Câu 2.** Method `String find() { return null; }` có lỗi biên dịch không?

**Trả lời:** Không. Declared return type là reference `String` nên `null` hợp lệ; caller cần xử lý khả năng null.

**Câu 3.** Nếu `int[] getNumbers()` trả thẳng mảng nội bộ, caller có thể thay đổi mảng nội bộ không?

**Trả lời:** Có, nếu caller có tham chiếu và mảng không được sao chép; ví dụ `getNumbers()[0] = 9` sẽ sửa mảng được chia sẻ.

**Câu 4.** `Integer getScore()` trả null; vì sao `int score = getScore();` có thể ném `NullPointerException`?

**Trả lời:** Gán sang `int` gây unboxing; không thể unbox tham chiếu null.

**Câu 5.** `Optional<String> findName()` nên trả `null` hay `Optional.empty()` khi thiếu dữ liệu?

**Trả lời:** Trả `Optional.empty()`. Trả null làm caller vừa phải kiểm tra null vừa xử lý Optional, trái với hợp đồng mong muốn.

**Câu 6.** Nếu method trả `new ArrayList<>(source)`, các phần tử mutable bên trong có được copy sâu không?

**Trả lời:** Không. Danh sách mới sao chép cấu trúc, còn tham chiếu đến phần tử có thể vẫn trỏ cùng object.

**Câu 7.** Hai lần gọi method `getCount()` trả `int` có chắc chắn cùng một số không?

**Trả lời:** Không. Field có thể thay đổi giữa hai lần gọi do command khác hoặc thread khác; method trả bản sao **tại lần đọc**, không cam kết trạng thái mãi mãi không đổi.

**Câu 8.** Một method `void save()` có phải trả về `null` khi chạy xong không?

**Trả lời:** Không. `void` nghĩa là không có giá trị kết quả; không thể gán kết quả gọi `save()` vào biến `Object` hoặc `String`.

### Checklist khi thiết kế method trả kết quả

1. **Khẳng định kiểu trả về:** primitive, reference hay `void`?
2. **Xác định ý nghĩa kết quả thiếu:** có thể `null` không, hay cần Optional, empty collection, exception hoặc kiểu kết quả riêng?
3. **Với reference, xác định ownership:** là object nội bộ, snapshot, copy hay instance mới?
4. **Đánh giá mutability:** caller có thể sửa object được trả về và phá invariant của class không?
5. **Xử lý chuyển đổi kiểu:** có boxing/unboxing, widening, ép kiểu hoặc null-unboxing nào gây lỗi không?
6. **Viết hợp đồng cho caller:** giá trị có thể null hay không, có cần đóng resource không, liệu kết quả có an toàn khi dùng ở thread khác không?
7. **Kiểm thử cả giá trị và hiệu ứng:** kết quả đúng, trường hợp không tìm thấy được xử lý, và không xuất hiện thay đổi trạng thái ngoài hợp đồng.

Hiểu đúng `return` nghĩa là hiểu **giá trị được trả**, **object mà giá trị tham chiếu trỏ tới**, và **ý nghĩa của sự vắng mặt (`null`)**. Ba điểm này giúp viết API Java rõ ràng, tránh lỗi null và kiểm soát việc chia sẻ trạng thái giữa các đối tượng.
