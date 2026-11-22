# Kiểu thô (raw type) là gì và vai trò trong mã Java trước generics

## Mục tiêu

**Raw type** là cách dùng một kiểu generic nhưng **không cung cấp đối số kiểu**, ví dụ viết `List` thay vì `List<String>` hoặc `List<?>`. Hiểu raw type giúp đọc và tích hợp các thư viện, lớp, phương thức viết trước khi Java hỗ trợ generics, đồng thời nhận ra vị trí mà compiler không thể kiểm tra đầy đủ tính an toàn kiểu.

Sau bài này, bạn có thể:

- Phân biệt kiểu generic, kiểu tham số hóa và raw type bằng ví dụ Java thực tế.
- Giải thích vì sao mã Java trước phiên bản 5 thường dùng `List`, `Object`, phép cast và vì sao Java vẫn hỗ trợ cách viết đó.
- Nắm vai trò của **type erasure**, **backward compatibility** và **migration compatibility** trong sự tồn tại của raw type.
- Đọc đúng cảnh báo `[rawtypes]`, `[unchecked]`, xác định lúc nào heap pollution và `ClassCastException` có thể xuất hiện.
- Chọn `List<?>`, `List<Object>`, `List<T>` hay một adapter có kiểm tra phần tử thay cho raw type.
- Biết cách khoanh vùng tiếp xúc với API legacy, từng bước chuyển mã cũ sang generics mà không tạo cảm giác an toàn giả.

## 1. Nhận biết raw type trong mã nguồn

Với interface `List<E>` và lớp `ArrayList<E>` trong `java.util`:

```java
List<String> names = new ArrayList<>(); // Parameterized type.
List<?> unknown = names;                // Parameterized type với wildcard.
List raw = names;                       // Raw type.
```

Các đoạn trên minh họa khai báo trong ngữ cảnh có import `java.util.List` và `java.util.ArrayList`. Sự khác biệt là:

| Cách viết | Ý nghĩa ở compile time | Có phải raw type? |
| --- | --- | --- |
| `List<String>` | Danh sách được khai báo có phần tử kiểu `String` | Không |
| `List<Integer>` | Danh sách được khai báo có phần tử kiểu `Integer` | Không |
| `List<Object>` | Danh sách được khai báo có phần tử kiểu `Object` | Không |
| `List<?>` | Danh sách với kiểu phần tử cụ thể chưa biết | Không |
| `List<E>` bên trong khai báo generic | Có tham số kiểu `E` | Không |
| `List` | Cách dùng kiểu generic mà bỏ đối số kiểu | **Có** |
| `ArrayList` | Cách dùng lớp generic mà bỏ đối số kiểu | **Có** |

Raw type xuất hiện khi tên lớp/interface generic được dùng **không có phần tham số kiểu**. Ví dụ:

```java
class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

Với lớp trên, `Box<String>` là kiểu tham số hóa; chỉ viết `Box` làm kiểu biến hoặc tham số là dùng **raw `Box`**.

Một điểm dễ nhầm: `Object` bản thân **không** là raw type. Nó là kiểu thông thường không khai báo tham số generic. `List<Object>` cũng **không phải raw type** vì đã chỉ rõ đối số kiểu `Object`.

## 2. Vì sao raw type có mặt trong lịch sử Java?

Java có `java.util.List` và các collection trước khi ngôn ngữ có generics. Trước **Java 5 (2004)**, code thường có hình dạng:

```java
import java.util.ArrayList;
import java.util.List;

class OldStyleExample {
    public static void main(String[] args) {
        List names = new ArrayList();
        names.add("Lan");
        names.add("Minh");

        String first = (String) names.get(0);
        System.out.println(first); // Lan
    }
}
```

Ngày nay đoạn chương trình vẫn biên dịch bằng JDK hiện đại; khi bật `-Xlint:rawtypes` và `-Xlint:unchecked`, compiler cảnh báo những chỗ dùng raw generic hoặc thao tác không được kiểm tra. Đây là **mã theo phong cách lịch sử**, không có nghĩa lập trình viên thời trước Java 5 đã có generic `List<E>` để cố ý bỏ đối số kiểu.

Vì chưa có generics, `List` lưu các tham chiếu dạng `Object`. `get(int)` trả về `Object`, người gọi phải cast thủ công nếu muốn dùng như `String`:

```java
String first = (String) names.get(0);
```

Những vấn đề của cách viết cũ:

- Không có cam kết cấp ngôn ngữ rằng danh sách chỉ chứa `String`.
- Có thể thêm một `Integer` vào danh sách chứa chuỗi mà compiler không bác bỏ vì nội dung cụ thể không được mô tả trong kiểu.
- Cast sai chỉ bị phát hiện khi chạy và có thể ném `ClassCastException`.
- Mỗi chỗ đọc phải chủ động cast; việc thay đổi API và bảo trì phức tạp hơn.

Từ Java 5, generics cho phép chỉ định `List<String>` để compiler kiểm tra việc thêm/lấy phần tử:

```java
List<String> names = new ArrayList<>();
names.add("Lan");
// names.add(123); // Không biên dịch.
String first = names.get(0); // Không cần tự viết cast trong source.
```

Một số thay đổi tạo nên cải tiến: compiler biết các phép gọi qua `List<String>` có kiểu phần tử `String`, hỗ trợ suy luận kiểu và cảnh báo/lỗi ngay lúc biên dịch. Compiler vẫn có thể tự chèn cast vào bytecode theo cơ chế type erasure.

Raw type tiếp tục tồn tại vì Java cần **tương thích với mã và thư viện cũ** đã viết trước generics, giúp mã cũ vẫn có thể sử dụng các lớp collection đã được tổng quát hóa.

## 3. Raw type liên quan thế nào đến type erasure?

Java generics chủ yếu kiểm tra kiểu tại **compile time**. Trong quá trình biên dịch, tham số kiểu được xóa khỏi JVM descriptor ở các vị trí thích hợp. Với tham số kiểu không có bound:

```java
class Box<T> {
    private T value;
    void set(T value) { this.value = value; }
    T get() { return value; }
}
```

`T` có erasure là `Object`. Các descriptor tiêu biểu:

| Thành phần trong source | Descriptor của JVM |
| --- | --- |
| Field `T value` | `Ljava/lang/Object;` |
| `void set(T value)` | `(Ljava/lang/Object;)V` |
| `T get()` | `()Ljava/lang/Object;` |
| `List<E>.add(E)` với `E` không bound | `(Ljava/lang/Object;)Z` |
| `List<E>.get(int)` | `(I)Ljava/lang/Object;` |

Điều này giúp mã sử dụng các phiên bản API trước generics tiếp tục có khả năng liên kết với bytecode phù hợp. Ví dụ, khi thư viện collection thêm metadata generic `List<E>` ở mã nguồn, các descriptor cơ bản như `get(int):Object` không đột ngột biến thành `get(int):String` theo từng cách gọi. Không có runtime class riêng `ArrayList<String>` và `ArrayList<Integer>` cho từng đối số generic.

**Tuy vậy raw type và erasure không phải một khái niệm.**

- **Type erasure** là cách compiler biểu diễn và dịch generic sang bytecode.
- **Raw type** là cách lập trình viên **viết một tham chiếu tới kiểu generic mà không có type arguments** ở mã nguồn.
- Một phương thức generic được dùng đúng với `List<String>` cũng trải qua erasure; không phải cứ erasure là code đã dùng raw type.
- Raw type bỏ bớt thông tin kiểm tra kiểu ở source, vì vậy có thể dẫn đến cảnh báo unchecked.

Việc compiler biên dịch generics bằng erasure cho phép tương thích runtime với code cũ; raw type là cầu nối cú pháp để tương tác với mã nguồn/API theo phong cách cũ.

## 4. Ví dụ đầy đủ: raw type có thể làm hỏng dữ liệu typed

Tạo tệp **`RawTypeDemo.java`**, Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeDemo {
    static class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    // API theo phong cách trước Java 5: List không có type argument.
    static void legacyAppend(List list, Object value) {
        list.add(value);
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        legacyAppend(words, 42);
        System.out.println("list data: " + words);

        try {
            String second = words.get(1);
            System.out.println(second);
        } catch (ClassCastException ex) {
            System.out.println("list read: " + ex.getClass().getSimpleName());
        }

        Box<String> box = new Box<>("safe");
        Box rawBox = box;
        rawBox.set(123);
        try {
            String value = box.get();
            System.out.println(value);
        } catch (ClassCastException ex) {
            System.out.println("box read: " + ex.getClass().getSimpleName());
        }
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawTypeDemo.java
java RawTypeDemo
```

Stdout chương trình **đã kiểm tra bằng JDK**:

```text
list data: [Java, 42]
list read: ClassCastException
box read: ClassCastException
```

Compiler cũng cảnh báo, chẳng hạn `[rawtypes] found raw type: List` và `[unchecked] unchecked call to add(E)` hay `set(T)`. Nội dung hiển thị cụ thể của cảnh báo phụ thuộc phiên bản compiler và vị trí dòng; đây không phải stdout của `java RawTypeDemo`.

### Diễn biến chính xác

1. `words` được khai báo `List<String>`, nên những lời gọi bình thường như `words.add(42)` **không biên dịch**.
2. `legacyAppend` nhận raw `List`; khi truyền `words` vào, phương thức nhận cùng một đối tượng danh sách. `list.add(42)` không được kiểm tra như thao tác của `List<String>` và compiler phát cảnh báo unchecked trong thân phương thức.
3. Nội dung thật của danh sách bây giờ là `[Java, 42]`, dù biến `words` vẫn được khai báo `List<String>`. Tình trạng dữ liệu không phù hợp với lời hứa generic này gọi là **heap pollution**.
4. Khi `String second = words.get(1)`, compiler dựa vào `List<String>` và có thể sinh `checkcast String`. Giá trị thật là `Integer`, nên `ClassCastException`.
5. Với `Box<String>`, gán `Box rawBox = box` không tạo hộp thứ hai: cả hai biến tham chiếu cùng một instance. Gọi `rawBox.set(123)` làm nhiễm dữ liệu trong hộp. Lời đọc `String value = box.get()` thất bại khi cast.

**Điều cần rút ra:** raw type vẫn có thể chạy được và tương thích về binary, nhưng mất một phần bảo đảm kiểm tra kiểu ở compile time. Lỗi có thể xuất hiện **muộn tại điểm đọc**, xa nơi dữ liệu sai kiểu được đưa vào.

## 5. Đọc đúng hai loại cảnh báo của compiler

Bật cả hai nhóm cảnh báo khi xem mã legacy:

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawTypeDemo.java
```

### `[rawtypes]`: dùng tên generic mà không có type argument

Ví dụ:

```java
List list = new ArrayList();
Box box = new Box("X");
```

Hai dòng này dùng raw `List`, raw `ArrayList`, raw `Box`. Với `-Xlint:rawtypes`, compiler cảnh báo sự thiếu vắng tham số kiểu. Cảnh báo `rawtypes` giúp chỉ ra nơi có thể cải thiện API để diễn tả dữ liệu rõ hơn.

### `[unchecked]`: một phép thao tác/biến đổi không thể được compiler kiểm tra đầy đủ

Ví dụ:

```java
List raw = new ArrayList();
raw.add("A"); // Unchecked call tới add(E) qua raw List.

List<String> words = raw; // Unchecked conversion từ raw List.
```

Ở thời điểm gán, compiler không thể xác minh toàn bộ phần tử trong raw list thật sự là `String`. Việc gán có thể biên dịch nhưng phát cảnh báo unchecked, tạo điều kiện dẫn đến `ClassCastException` khi dữ liệu được lấy ra.

Bảng phân biệt:

| Cảnh báo | Chỉ ra điều gì? | Ví dụ |
| --- | --- | --- |
| `rawtypes` | Tên kiểu generic được dùng như raw type | `List list` |
| `unchecked` | Việc gọi/gán/cast liên quan generic không được kiểm tra đầy đủ | `raw.add(1)`, `List<String> x = raw` |
| Lỗi biên dịch | Compiler chứng minh được lời gọi typed không tương thích | `List<String> x; x.add(1)` |
| Lỗi runtime | Dữ liệu thực không phù hợp phép cast/giả định | `ClassCastException` khi đọc |

Hai cảnh báo có thể cùng xuất hiện tại các chỗ khác nhau; chúng **không đồng nghĩa**. Một khai báo raw không nhất thiết ngay lập tức gây lỗi runtime, và một unchecked cast có thể xuất hiện cả khi không có raw declaration gần đó. Tắt cảnh báo không làm chương trình an toàn hơn.

`@SuppressWarnings({"rawtypes", "unchecked"})` đôi khi cần thiết ở một adapter legacy đã được kiểm tra thủ công, nhưng không nên rải chú thích đó khắp code để loại cảnh báo mà chưa chứng minh dữ liệu đúng.

## 6. So sánh raw `List`, `List<?>`, `List<Object>` và `List<String>`

Sự khác biệt quan trọng không chỉ là cách viết:

| Kiểu biến | Có thể đọc thành | Có thể thêm `String`? | Có thể thêm `Integer`? |
| --- | --- | --- | --- |
| `List<String>` | `String` | Có | Không |
| `List<Object>` | `Object` | Có | Có |
| `List<?>` | `Object` | Không, trừ `null` | Không, trừ `null` |
| Raw `List` | `Object` | Có, với cảnh báo unchecked | Có, với cảnh báo unchecked |

Bảng giả định danh sách có thể sửa; với `List.of(...)` hoặc danh sách không hỗ trợ ghi, mọi lời gọi sửa đổi có thể ném `UnsupportedOperationException` ở runtime dù được phép theo kiểu Java.

### Vì sao `List<?>` tốt hơn raw `List` khi chỉ cần đọc?

```java
static void printElements(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
```

Đây là method dùng được khi đặt trong một class và import `java.util.List`. Nó chấp nhận `List<String>`, `List<Integer>` và nhiều loại danh sách khác nhưng **không cho phép tự ý nhét đối tượng vào danh sách khi chưa biết kiểu phần tử**.

Ngược lại, `static void printElements(List items)` đưa raw type vào API và mở khả năng gọi các phương thức ghi có cảnh báo unchecked. Nếu chỉ cần quan sát, `List<?>` diễn tả ý định an toàn và chính xác hơn.

### Vì sao không luôn thay raw `List` bằng `List<Object>`?

Vì `List<String>` **không phải subtype của** `List<Object>`. Generics của Java bất biến (*invariant*); phép gán:

```java
List<String> names = new ArrayList<>();
// List<Object> all = names; // Lỗi biên dịch.
List<?> any = names;         // Hợp lệ.
```

Nếu `List<String>` được xem như `List<Object>`, code khác có thể thêm `Integer` thông qua biến `all`, phá cam kết của `names`. Với API chỉ đọc, `List<?>` thường là cách thay raw type có tính tương thích tốt hơn `List<Object>`.

Nếu **đúng yêu cầu nghiệp vụ** là một danh sách có thể chứa nhiều loại giá trị khác nhau, `List<Object>` có ý nghĩa riêng; nó không phải giải pháp thay thế tùy tiện cho mọi `List<String>`.

## 7. Vai trò hợp lệ của raw type khi giao tiếp với API legacy

Raw type không xuất hiện chỉ do lập trình viên quên cú pháp. Nó còn là một phần trong chiến lược chuyển đổi giữa thế giới Java **trước** và **sau** generics.

Các tình huống thường thấy:

1. **Mã nguồn cũ** khai báo `List`, `Map`, `Class` hoặc container riêng như `Box` mà không có type arguments.
2. **API cũ** nhận/trả collection không có thông tin kiểu phần tử, vì hợp đồng API lúc được viết không có generics.
3. **Thư viện binary cũ** vẫn phải liên kết được với chương trình mới. Type erasure giúp các descriptor tương thích ở các trường hợp được thiết kế cho mục đích này.
4. **Quá trình nâng cấp dần**: có thể thay từng chỗ raw type bằng dạng generic, dùng adapter tại ranh giới thay vì bắt buộc viết lại toàn bộ ứng dụng cùng lúc.

Tuy nhiên, raw type nên được nhìn như **điểm tiếp xúc cần kiểm soát**, không phải cách thiết kế API generic mới. Khi thư viện đã có dạng generic tương ứng, ưu tiên tham số hóa kiểu theo dữ liệu thật.

Một nguyên tắc nâng cấp: đừng vội tuyên bố raw `List` chứa `String` chỉ vì dữ liệu thử nghiệm hiện tại có vẻ là chuỗi. Kiểm tra hợp đồng trả về từ thư viện hoặc kiểm tra từng phần tử trước khi xuất ra một `List<String>` được tin cậy.

## 8. Tạo một ranh giới đọc có kiểm tra khi gặp API cũ

Nếu code cũ trả raw `List` mà phía mới muốn bảo đảm tất cả phần tử là chuỗi, **không cast cả list thành `List<String>`**. Hãy đưa nguồn vào một API nhận `List<?>` rồi kiểm tra từng phần tử:

```java
static java.util.List<String> validatedNames(java.util.List<?> source) {
    java.util.List<String> result = new java.util.ArrayList<>();
    for (Object item : source) {
        result.add(String.class.cast(item));
    }
    return java.util.List.copyOf(result);
}
```

Đây là một **method minh họa** để đặt trong class; bài đã có chương trình độc lập `RawTypeDemo.java` ở phần 4 để quan sát raw write và late failure. Trong helper, `String.class.cast` xác minh runtime class của từng phần tử; `List.copyOf` từ chối `null` và tạo danh sách không cho chỉnh sửa qua API thông thường. Nếu muốn cho phép null, phải định nghĩa hợp đồng và dùng kết quả khác.

Đường kiểm tra này hữu ích khi **legacy interface chưa thể sửa**, nhưng phía hiện đại không muốn phát tán unchecked cast. Một bản adapter ở production còn cần làm rõ index khi dữ liệu sai, quyền sở hữu/cập nhật của list nguồn và việc sao chép có thực sự đủ. Bài ở đây chỉ giới thiệu chiến lược; chương trình di trú nhiều tầng, xử lý caller cũ và tương thích nhị phân cần được thiết kế tại phạm vi hệ thống.

## 9. Raw type khác wildcard ở kiểm tra khi biên dịch

Phần này thường gây nhầm:

```java
List<String> strings = new ArrayList<>();
List raw = strings;       // Raw type.
List<?> unknown = strings;
```

Khi viết:

```java
raw.add(100);
```

Trình biên dịch có thể cho phép lời gọi nhưng cảnh báo **unchecked**: raw type làm mất liên kết với đối số `String` trong tham chiếu đó.

Khi viết:

```java
// unknown.add(100); // Không biên dịch.
// unknown.add("X"); // Không biên dịch.
```

Compiler **không biết** wildcard cụ thể là kiểu nào, nên không cho phép ghi một đối tượng không phải `null`. Điều này giúp `List<?>` duy trì an toàn kiểu khi code chỉ cần đọc.

Cả `raw` và `unknown` đều là tham chiếu tới **chính danh sách `strings`**, không tạo bản sao. Khác biệt nằm ở **hợp đồng compile time** của hai kiểu tham chiếu.

Một ví dụ khác cần tránh:

```java
// if (obj instanceof List<String>) { } // Không hợp lệ vì type argument không reifiable.
if (obj instanceof List<?>) {
    // Biết obj là List, không kết luận phần tử bên trong là String.
}
```

Đoạn kiểm tra trên giả định đã có `Object obj` trong ngữ cảnh. `List<?>` là trường hợp có thể kiểm tra bằng `instanceof`, còn `List<String>` không phải một runtime class chuyên biệt để kiểm tra trực tiếp.

## 10. Một raw type không xóa mọi giới hạn kiểu

Có một ngoại lệ cần hiểu đúng khi suy luận: nếu type parameter **có upper bound**, erasure thường dùng upper bound đó, không luôn là `Object`.

Ví dụ minh họa:

```java
class NumberHolder<T extends Number> {
    void accept(T number) {
        System.out.println(number);
    }
}
```

Sau erasure, `accept(T)` có descriptor nhận `Number`. Nếu dùng:

```java
NumberHolder rawHolder = new NumberHolder();
rawHolder.accept(Integer.valueOf(7)); // Hợp lệ.
// rawHolder.accept("text");           // Vẫn là lỗi biên dịch.
```

Đoạn trên cần đặt vào một class/method phù hợp để chạy; nó tập trung giải thích chữ ký. Dù `rawHolder` là raw type, phương thức nhận `Number` sau erasure, nên `String` không thể truyền thẳng vào. Không thể kết luận rằng raw type cho phép **mọi kiểu giá trị** ở **mọi phương thức**.

Nếu mã đang dùng `Box<T extends Number>`, khả năng can thiệp từ raw type phải được phân tích theo bound và chữ ký erased thật. Raw type làm giảm thông tin generic, nhưng các ràng buộc còn được biểu diễn trong chữ ký erased vẫn có hiệu lực.

## 11. Định hướng chuyển đổi khi bắt gặp raw API

Trong codebase lâu năm, raw type có thể xuất hiện ở một chỗ khai báo, trong chữ ký method, hoặc được truyền tới các callers khác. Hãy bắt đầu với **mục đích sử dụng** thay vì thay tất cả `List` thành `List<Object>`:

| Bối cảnh | Hành động ưu tiên | Vì sao |
|---|---|---|
| Sở hữu dữ liệu và biết chắc chỉ chứa `String` | Sửa nơi tạo, nơi ghi và chữ ký thành `List<String>` | Compiler bảo vệ invariant từ nguồn |
| Không biết element type, chỉ cần quan sát | Nhận `List<?>` | Không cho mã quan sát thêm non-null tùy ý |
| API legacy trả raw `List`, ứng dụng cần `List<String>` | Dùng helper kiểm tra từng phần tử rồi copy | Không biến unchecked cast thành lời hứa giả |
| Chưa thể chứng minh element type | Giữ `List<?>` và xử lý như `Object` | Trung thực với thông tin hiện có |

Bật `javac -Xlint:rawtypes,unchecked` để định vị raw declarations và unchecked operations. Việc biên dịch vẫn thành công với warning không chứng minh dữ liệu an toàn. Nếu phải để một raw boundary tồn tại, cô lập nó và dùng tests với dữ liệu sai loại trước khi công bố API typed.

**Điểm kết nối:** Phân biệt chiều chuyển đổi raw/parameterized, cách type erasure tác động tới members và kế hoạch di trú caller/callee là các bước tiếp theo; định nghĩa nền tảng của raw type không tự quyết định toàn bộ phương án migration.

## 12. Các lỗi phổ biến

### Nhầm raw `List` với `List<Object>`

`List<Object>` có type argument rõ ràng, cho phép chứa nhiều loại đối tượng nhưng không thể nhận trực tiếp tham chiếu `List<String>` do invariance. Raw `List` bỏ kiểm tra tham số generic và có thể phát cảnh báo.

### Thấy “biên dịch được” là cho rằng “an toàn”

Unchecked warning là thông tin compiler **không chứng minh được** thao tác an toàn. Chạy được với dữ liệu thử không bảo đảm an toàn khi dữ liệu thay đổi.

### Đọc `List<String>` sau khi nguồn raw đã thêm giá trị sai

Compiler vẫn xem biểu thức `words.get(i)` có kiểu nguồn `String`; khi cast do compiler chèn kiểm tra giá trị thực là `Integer`, lỗi có thể xảy ra. Vì thế vị trí ném lỗi thường là chỗ **đọc/ép kiểu**, không nhất thiết là chỗ thêm dữ liệu sai.

### Coi `List<?>` là raw vì nó không nêu kiểu cụ thể

`List<?>` vẫn là **kiểu tham số hóa**, mang ràng buộc wildcard và hạn chế thao tác ghi để giữ an toàn. Nó là lựa chọn phù hợp khi API chỉ cần xem nội dung của một danh sách có kiểu chưa biết.

### Ép `Object` hoặc `Class` mà không xác minh

`Object` và raw `Class` không tự cung cấp thông tin về mọi đối số generic. Muốn khôi phục kiểu dữ liệu ở ranh giới, cần contract hoặc metadata/thao tác kiểm tra đáng tin cậy.

### Dùng `@SuppressWarnings` để tắt toàn bộ cảnh báo trong dự án

Suppression rộng có thể che các unchecked calls mới, khiến vấn đề khó truy vết. Giữ raw type trong module biên khi bất khả kháng, và cố gắng để phần lớn code dùng các kiểu tham số hóa.

### Quên rằng raw collection vẫn có thể không sửa được

`List raw = List.of("A")` là raw reference tới danh sách không hỗ trợ sửa. Dù compiler có thể cho phép `raw.add("B")` với unchecked warning, lời gọi vẫn có thể ném `UnsupportedOperationException`. Raw type không thay đổi các giới hạn về khả năng sửa của đối tượng thực.

## 13. Bài tập tự kiểm tra

**Bài 1 — Phân loại kiểu.** Trong các dạng `List`, `List<?>`, `List<Object>`, `List<String>`, dạng nào là raw type?

**Đáp án:** chỉ `List` không có đối số kiểu.

**Bài 2 — Dự đoán cảnh báo.** Với `List raw = new ArrayList(); raw.add(1);`, `-Xlint:rawtypes` và `-Xlint:unchecked` có ý nghĩa gì?

**Đáp án:** `rawtypes` phát hiện chỗ không cung cấp đối số generic; `unchecked` cảnh báo lời gọi `add(E)` qua raw reference không được kiểm tra như một lời gọi typed.

**Bài 3 — Phân tích lỗi muộn.**

```java
List<String> words = new ArrayList<>();
List raw = words;
raw.add(99);
String s = words.get(0);
```

Đoạn minh họa cần đặt trong method có import collection. Vì sao lỗi phát sinh ở dòng cuối, dù dòng `add` đã chạy?

**Đáp án:** raw `List` cho phép một giá trị `Integer` đi vào đối tượng danh sách với cảnh báo; tại `words.get(0)`, code typed kỳ vọng `String` và cast thất bại.

**Bài 4 — Chọn chữ ký.** Một method chỉ duyệt và in mọi phần tử của danh sách bất kể kiểu, nên nhận `List`, `List<Object>` hay `List<?>`?

**Đáp án:** `List<?>`, vì chấp nhận các dạng danh sách typed khác nhau và không cho phép tùy tiện thêm phần tử.

**Bài 5 — Phân biệt erasure.** Vì sao `List<String>` vẫn bị erasure mặc dù nó không phải raw type?

**Đáp án:** erasure là cơ chế biên dịch chung cho generics; raw type chỉ là kiểu tham chiếu ở Java source khi bỏ đối số generic.

**Bài 6 — Nâng cấp API cũ.** Thư viện cũ trả `List` có thể chứa cả `String` lẫn `Integer`. Bạn cần API trả `List<String>`. Có nên cast cả danh sách thành `List<String>`?

**Đáp án:** không thể coi unchecked cast đó là bằng chứng an toàn. Cần xác minh từng phần tử, từ chối phần tử sai, tạo collection typed mới, hoặc công bố đúng kiểu dữ liệu thực nếu không thể bảo đảm.

**Bài 7 — Raw type có còn bound không?** Với `NumberHolder<T extends Number>`, gọi `rawHolder.accept("hello")` có hợp lệ không?

**Đáp án:** không. Erasure của `T` là `Number`, nên `String` vẫn không phù hợp với chữ ký nhận `Number`.

## Kết luận thực hành

**Raw type là tên một lớp/interface generic được dùng mà không cung cấp type arguments**, như `List` hay `Box`. Nó tồn tại chủ yếu để các API và chương trình Java cũ có thể tiếp tục sống cùng generics được bổ sung từ Java 5. Cơ chế **type erasure** hỗ trợ tương thích binary, nhưng việc dùng raw type ở mã nguồn làm giảm kiểm tra an toàn kiểu và có thể mở đường cho **unchecked calls, heap pollution và `ClassCastException`**.

Khi viết Java hiện đại, hãy khai báo kiểu cụ thể như `List<String>` nếu biết dữ liệu; dùng `List<?>` nếu chỉ cần đọc một danh sách chưa biết kiểu; dùng `List<Object>` khi thật sự cần chứa nhiều loại đối tượng; và khoanh raw type ở ranh giới tích hợp với mã legacy. **Giữ cảnh báo compiler hữu ích, kiểm tra dữ liệu tại ranh giới và tránh unchecked cast tùy tiện** là cách tận dụng tương thích với mã cũ mà vẫn duy trì tính an toàn kiểu của ứng dụng.
