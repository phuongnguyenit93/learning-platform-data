# Kiểm tra và chuyển kiểu bằng Class.cast, Class.asSubclass

## Khái niệm: kiểm tra đối tượng khác với kiểm tra một kiểu

Khi viết reflection, thông tin kiểu thường chỉ xuất hiện khi chương trình chạy:

- Một giá trị được nhận dưới dạng `Object`.
- Một kiểu được phát hiện dưới dạng `Class<?>`, chẳng hạn từ một tên lớp trong cấu hình.

Nếu cần đưa chúng về hợp đồng kiểu mà phần mã còn lại hiểu được, Java cung cấp hai API khác mục tiêu:

| API | Đầu vào được kiểm tra | Kết quả |
| --- | --- | --- |
| `expected.cast(value)` | Một đối tượng có dùng được như kiểu `expected` không? | Cùng tham chiếu đối tượng, được trả về với kiểu tĩnh tương ứng |
| `candidate.asSubclass(base)` | Kiểu `candidate` có gán được cho kiểu `base` không? | Cùng đối tượng `Class`, với thông tin generic được thu hẹp |

Ví dụ:

- `String.class.cast(value)`: hỏi về **giá trị** `value`.
- `candidate.asSubclass(Handler.class)`: hỏi về **kiểu mà candidate đại diện**.

Hai API này vẫn được dùng trong Java hiện đại. Bài dùng ví dụ chạy được trên JDK 17 trở lên.

## Vì sao chúng hữu ích trong mã generic và reflection?

Với kiểu biết sẵn khi viết mã, có thể dùng một phép ép kiểu thông thường như `(String) value`. Nhưng một hàm dùng chung có thể nhận kiểu mong đợi qua tham số `Class<T>`, thay vì viết cố định `String`.

`Class<T>` đóng vai trò một giá trị mang thông tin kiểu tại lúc chạy, thường gọi là **type token**. Hàm có thể dùng token để thực hiện phép kiểm tra thực sự:

```java
static <T> T checkedValue(Class<T> expected, Object value) {
    return expected.cast(value);
}
```

Đây là phương thức minh họa, được đặt trong chương trình hoàn chỉnh phía dưới.

Hàm không tự suy ra `T` từ một phép ép kiểu không được kiểm tra. Nó sử dụng đối tượng `Class<T>` mà phía gọi cung cấp. Chẳng hạn, truyền `String.class` cho phép kết quả có kiểu tĩnh `String` và đồng thời kiểm tra đối tượng bằng kiểu thực tế khi chạy.

Với `Class<?>`, `asSubclass` giải quyết vấn đề tương tự ở cấp kiểu: xác nhận kiểu vừa được phát hiện đáp ứng hợp đồng `Handler`, rồi biểu diễn kết quả bằng `Class<? extends Handler>`.

## Class.cast: kiểm tra rồi trả chính đối tượng

Chữ ký quan trọng trên `Class<T>` là:

```java
public T cast(Object obj)
```

Hành vi cần nhớ:

1. Nếu đối tượng khác `null` và phù hợp với kiểu mà `Class` đại diện, trả về cùng tham chiếu đó.
2. Nếu đối tượng không phù hợp, ném `ClassCastException`.
3. Nếu đối số là `null`, trả về `null`.

Ví dụ minh họa bên trong một phương thức:

```java
Object raw = "java";
String text = String.class.cast(raw);
Number number = Number.class.cast(Integer.valueOf(7));
```

Trường hợp thứ hai không yêu cầu kiểu của đối tượng phải đúng bằng `Number`. Một `Integer` dùng được như `Number`, nên phép kiểm tra thành công.

`cast` không tạo bản sao, không biến đổi nội dung đối tượng và không chạy bộ chuyển đổi dữ liệu. `Integer.class.cast("7")` không phân tích chuỗi thành số. Nếu cần đọc số từ văn bản, phải dùng một thao tác như `Integer.parseInt` theo hợp đồng dữ liệu thích hợp.

API chính thức: [Class.cast](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)).

### Giá trị null cần được xử lý theo yêu cầu của ứng dụng

`String.class.cast(null)` hợp lệ và trả `null`. Vì vậy, phép cast thành công không chứng minh giá trị bắt buộc đã có.

Nếu hàm yêu cầu khác `null`, cần quy định và kiểm tra điều đó riêng, chẳng hạn bằng `Objects.requireNonNull`. Kiểm tra “đúng kiểu” và kiểm tra “không thiếu giá trị” là hai điều kiện khác nhau.

Cũng phân biệt `value == null` với `expected == null`: gọi `expected.cast(value)` khi chính biến `expected` là `null` sẽ gây `NullPointerException`, không phải một phép kiểm tra kiểu thất bại có chủ ý.

## Class.asSubclass: thu hẹp thông tin kiểu của Class

Chữ ký:

```java
public <U> Class<? extends U> asSubclass(Class<U> clazz)
```

Cách đọc:

- Đối tượng nhận lời gọi là `candidate`: kiểu cần được xác nhận.
- Đối số `clazz` là kiểu cơ sở hoặc interface mong đợi.
- Kết quả là một `Class` đại diện cho kiểu có thể dùng như một kiểu con của `U`.

Ví dụ minh họa:

```java
Class<?> candidate = GreetingHandler.class;
Class<? extends Handler> handlerType =
        candidate.asSubclass(Handler.class);
```

Nếu `GreetingHandler` triển khai `Handler`, phép kiểm tra thành công. Dù tên API chứa “Subclass”, nó cũng dùng được với quan hệ triển khai interface.

Nếu quan hệ không phù hợp, ném `ClassCastException`. Kết quả thành công vẫn là chính đối tượng `Class` ban đầu; API không tạo một lớp mới và cũng không tạo đối tượng nghiệp vụ.

Quan hệ tương thích này bao gồm trường hợp kiểu ứng viên chính là kiểu cơ sở. Ví dụ, `Handler.class.asSubclass(Handler.class)` có thể hợp lệ, nhưng `Handler` là interface nên vẫn không thể tạo một đối tượng trực tiếp bằng constructor của interface.

API chính thức: [Class.asSubclass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#asSubclass(java.lang.Class)).

### Vì sao không ép kiểu Class<?> một cách thủ công?

Đoạn minh họa sau có vấn đề về kiểm tra generic:

```java
// Minh họa cách cần tránh khi chỉ muốn xác nhận quan hệ kiểu:
Class<? extends Handler> type =
        (Class<? extends Handler>) candidate;
```

Với `candidate` là `Class<?>`, phép ép này tạo cảnh báo unchecked: JVM không dùng tham số generic của `Class` để tự chứng minh kiểu mà token đại diện thực sự triển khai `Handler`.

`candidate.asSubclass(Handler.class)` thực hiện kiểm tra quan hệ ở lúc chạy và trả kiểu generic đúng cho phần mã tiếp theo. Không cần che cảnh báo bằng `@SuppressWarnings("unchecked")` cho mục đích này.

## Chương trình đầy đủ: kiểm tra giá trị và kiểu được phát hiện

Lưu thành `ClassConversionDemo.java`:

```java
public class ClassConversionDemo {
    public interface Handler {
        String handle();
    }

    public static class GreetingHandler implements Handler {
        public GreetingHandler() {
        }

        @Override
        public String handle() {
            return "hello";
        }
    }

    public static class Unrelated {
        public Unrelated() {
        }
    }

    static <T> T checkedValue(Class<T> expected, Object value) {
        return expected.cast(value);
    }

    static Class<? extends Handler> handlerClass(Class<?> candidate) {
        return candidate.asSubclass(Handler.class);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Object value = "java";
        String text = checkedValue(String.class, value);
        System.out.println("cast=" + text);
        System.out.println("null=" + (String.class.cast(null) == null));

        try {
            Integer.class.cast(value);
        } catch (ClassCastException ex) {
            System.out.println("badObject="
                    + ex.getClass().getSimpleName());
        }

        Class<?> discovered = Class.forName(
                GreetingHandler.class.getName(), false,
                ClassConversionDemo.class.getClassLoader());
        Class<? extends Handler> narrowed = handlerClass(discovered);
        Handler handler = narrowed.getDeclaredConstructor().newInstance();
        System.out.println("handler=" + handler.handle());

        try {
            handlerClass(Unrelated.class);
        } catch (ClassCastException ex) {
            System.out.println("badClass="
                    + ex.getClass().getSimpleName());
        }

        Number number = Number.class.cast(Integer.valueOf(7));
        System.out.println("supertype=" + number.intValue());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 ClassConversionDemo.java
java ClassConversionDemo
```

Kết quả:

```text
cast=java
null=true
badObject=ClassCastException
handler=hello
badClass=ClassCastException
supertype=7
```

### Giải thích từng nhóm kết quả

`checkedValue(String.class, value)` xác nhận `value` là đối tượng có thể dùng như `String`. Kết quả có kiểu tĩnh `String`, không cần phép ép ở nơi gọi.

`String.class.cast(null)` trả `null`, nên dòng kiểm tra in `true`.

`Integer.class.cast(value)` thất bại vì `value` đang tham chiếu đến một chuỗi. Không có chuyển đổi từ chuỗi sang số.

`Class.forName` phát hiện kiểu qua tên nhị phân lấy từ `GreetingHandler.class.getName()`. Vì `GreetingHandler` là lớp lồng nhau trong ví dụ, cách lấy tên này tránh viết nhầm tên nhị phân bằng tên dùng trong mã nguồn.

Sau đó:

1. `discovered` có kiểu `Class<?>`: mã chưa có cam kết generic rằng đây là một `Handler`.
2. `handlerClass(discovered)` dùng `asSubclass` để kiểm tra.
3. `narrowed` có kiểu `Class<? extends Handler>`.
4. `getDeclaredConstructor().newInstance()` tạo đối tượng qua constructor không tham số.
5. Đối tượng được gán cho `Handler`, rồi gọi `handle()`.

`Unrelated.class` không đáp ứng `Handler`, nên bị từ chối ngay ở bước `asSubclass`, trước thao tác tạo đối tượng.

Cuối cùng, `Number.class.cast(Integer.valueOf(7))` thành công vì kiểu của đối tượng tương thích qua quan hệ kiểu cha, không cần trùng chính xác.

## Kiểm tra trước khi chuyển: isInstance và isAssignableFrom

Nếu việc không tương thích là một kết quả bình thường cần phân nhánh, có thể kiểm tra trước thay vì dùng ngoại lệ làm nhánh điều khiển chính.

| Câu hỏi | Phép kiểm tra boolean | Thao tác trả về kiểu đã thu hẹp |
| --- | --- | --- |
| Đối tượng này dùng được như kiểu mong đợi không? | `expected.isInstance(value)` | `expected.cast(value)` |
| Kiểu này dùng được như kiểu cơ sở không? | `base.isAssignableFrom(candidate)` | `candidate.asSubclass(base)` |

Chú ý thứ tự đối số:

```java
// Các biểu thức minh họa:
Handler.class.isAssignableFrom(GreetingHandler.class);
GreetingHandler.class.asSubclass(Handler.class);
```

Hai biểu thức cùng hướng tới quan hệ “`GreetingHandler` dùng được như `Handler`”, nhưng kiểu cơ sở đứng ở vị trí khác nhau.

`expected.isInstance(null)` trả `false`, trong khi `expected.cast(null)` trả `null`. Nếu muốn chấp nhận null, không được viết một phép kiểm tra `isInstance` rồi mặc nhiên coi nó tương đương hoàn toàn với hành vi của `cast`.

Ví dụ, trong một hàm nhận `Class<T> expected` và `Object value`, có thể chủ động định nghĩa quy tắc:

```java
if (value == null || expected.isInstance(value)) {
    T result = expected.cast(value);
    // Xử lý result theo hợp đồng có chấp nhận null.
}
```

Đây là mảnh minh họa, không phải chương trình độc lập và cũng không thay thế kiểm tra bắt buộc khác null nếu nghiệp vụ yêu cầu.

## Kiểm tra đúng kiểu chưa đủ để khởi tạo

`asSubclass` chỉ xác nhận quan hệ kiểu. Nó không xác nhận:

- Ứng viên là lớp cụ thể thay vì interface hoặc lớp abstract.
- Có constructor không tham số.
- Constructor có quyền truy cập phù hợp.
- Constructor sẽ chạy thành công.
- Khởi tạo lớp và các phụ thuộc của nó sẽ không lỗi.
- Đối tượng đáp ứng yêu cầu nghiệp vụ ngoài hợp đồng kiểu.

Ví dụ, một lớp abstract triển khai `Handler` vẫn có thể qua `asSubclass(Handler.class)`, nhưng không thể được khởi tạo như một lớp cụ thể bình thường.

Trong chương trình, `GreetingHandler` là lớp public lồng static, có constructor public không tham số để bước tạo đối tượng rõ ràng. Thí nghiệm không cần vượt quyền truy cập hoặc dùng `setAccessible`.

Nếu phát triển bộ nạp thành phần, phải tách chẩn đoán theo giai đoạn: nạp lớp, kiểm tra quan hệ, tìm constructor, gọi constructor và sử dụng đối tượng. `ClassCastException` ở bước kiểm tra quan hệ không phải cùng lỗi với `NoSuchMethodException` khi thiếu constructor hay lỗi được constructor ném ra.

Dùng `getDeclaredConstructor().newInstance()` cho việc khởi tạo phản chiếu phù hợp; không cần API `Class.newInstance()` đã được đánh dấu deprecated.

## Giới hạn với generic do xóa kiểu

`Class` phản ánh kiểu có thể nhận diện tại lúc chạy; nó không tự cung cấp một token khác nhau cho mọi cách gắn tham số generic.

Không có class literal hợp lệ dạng:

```java
// Cố ý không hợp lệ:
List<String>.class
```

`List.class.cast(value)` có thể xác nhận đối tượng là một `List`, nhưng không xác nhận từng phần tử là `String`.

Tương tự, `asSubclass(List.class)` không chứng minh một kiểu ứng viên đáp ứng yêu cầu “danh sách chỉ chứa chuỗi”. Đó là giới hạn khác với việc kiểm tra đối tượng có triển khai interface `List` hay không.

Nếu cần xác nhận nội dung phần tử, phải duyệt và kiểm tra hoặc dùng một mô hình dữ liệu có kiểm soát. Nếu cần mô tả chữ ký generic của khai báo, các API `Type`, `ParameterizedType` có vai trò riêng; thông tin chữ ký đó cũng không tự biến thành kiểm chứng nội dung của mọi đối tượng.

Xem nền tảng về kiểu có thể nhận diện khi chạy tại [JLS §4.7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.7).

## Kiểu nguyên thủy, boxing và chuyển đổi số

`int.class` là một đối tượng `Class` đại diện cho kiểu nguyên thủy; nó không phải `Integer.class`.

Các API này không phải bộ chuyển đổi số và không tạo một quy tắc boxing/unboxing tùy ý. Nếu giá trị được nhận qua `Object`, nó là một tham chiếu, chẳng hạn tới `Integer`; không có đối tượng là instance của kiểu nguyên thủy `int` theo cách kiểm tra instance thông thường.

Trong một hàm dùng token để kiểm tra giá trị đối tượng, nên xác định rõ cách hỗ trợ các kiểu bọc như `Integer.class`, hoặc xử lý riêng nếu giao diện cho phép token nguyên thủy. Không coi `int.class.cast(Integer.valueOf(3))` là phép unboxing thông thường.

Ngay cả với kiểu bọc, `Long.class.cast(Integer.valueOf(3))` cũng không chuyển số nguyên sang số dài. Cần một thao tác chuyển dữ liệu có chủ ý nếu hợp đồng yêu cầu điều đó.

## Danh tính kiểu và bộ nạp lớp

Trong môi trường plugin hoặc nhiều bộ nạp lớp (class loader), hai kiểu cùng tên đầy đủ không nhất thiết là cùng một kiểu lúc chạy.

Nếu một bản `Handler` được nạp ở ngữ cảnh khác với bản mà lớp ứng viên triển khai, `asSubclass` có thể thất bại dù tên hiển thị trông như khớp nhau. Kiểm tra chuỗi tên bằng `getName()` không thay thế được kiểm tra quan hệ kiểu thực tế.

Khi chẩn đoán, đối chiếu:

- Kiểu cơ sở mà mã đang dùng.
- Bộ nạp của kiểu cơ sở và kiểu ứng viên.
- Nguồn thư viện cung cấp từng kiểu.
- Bản sao phụ thuộc có bị đưa vào nhiều vùng nạp khác nhau không.

Chỉ cần xem chi tiết này khi môi trường có nhiều bộ nạp hoặc thành phần nạp động; không phải mọi `ClassCastException` đều do class loader.

## Khi nào dùng API nào?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Kiểu đã biết sẵn và mã thông thường | Phép ép kiểu hoặc `instanceof` khi cần |
| Hàm generic nhận `Class<T>` và `Object` | `Class.cast` |
| Phát hiện một lớp rồi cần xác nhận nó triển khai hợp đồng | `Class.asSubclass` |
| Cần kiểm tra boolean trước khi chấp nhận một giá trị | `Class.isInstance` |
| Cần kiểm tra boolean quan hệ hai token kiểu | `Class.isAssignableFrom` |
| Chuyển chuỗi sang số hoặc ánh xạ dữ liệu | Bộ phân tích/chuyển đổi dữ liệu riêng |
| Xác nhận nội dung generic như mọi phần tử đều là String | Kiểm tra nội dung hoặc mô hình dữ liệu phù hợp |

Không cần dùng reflection chỉ để thay một phép ép kiểu đơn giản ở nơi kiểu đã được biết rõ. Giá trị chính của hai API là nối thông tin kiểu động với hợp đồng generic của mã Java.

## Lỗi phổ biến

| Lỗi | Cách sửa suy luận |
| --- | --- |
| Dùng `cast` lên đối tượng `Class` để xác nhận kiểu được nó đại diện | Dùng `asSubclass` cho quan hệ giữa các kiểu |
| Cho rằng cast biến đổi dữ liệu | Nhớ rằng nó kiểm tra và trả cùng tham chiếu |
| Dùng `asSubclass` rồi cho rằng đã có đối tượng | Bước tạo đối tượng là thao tác riêng |
| Đảo chiều `isAssignableFrom` | Đặt kiểu đích/cơ sở làm đối tượng nhận lời gọi |
| Cho rằng cast thành công chứng minh khác null | Kiểm tra null riêng nếu cần |
| Che unchecked cast của `Class<?>` | Dùng `asSubclass` để có kiểm tra lúc chạy |
| Đòi kiểm chứng `List<String>` chỉ bằng `List.class` | Phân biệt kiểu danh sách với kiểu từng phần tử |
| Chỉ so sánh tên kiểu khi nạp động | Kiểm tra quan hệ thực tế và ngữ cảnh nạp lớp |

`ClassCastException` báo phép kiểm tra kiểu không tương thích, không phải yêu cầu Java tự tìm một cách chuyển đổi khác. Xem [ClassCastException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassCastException.html).

## Thực hành kiểm chứng

1. Chạy chương trình và đối chiếu đủ sáu dòng output.
2. Đổi giá trị đầu vào từ `"java"` sang `Integer.valueOf(8)`; quan sát nơi `checkedValue(String.class, value)` thất bại và giải thích vì sao nó không tự đổi số sang chuỗi.
3. Thêm một lớp khác triển khai `Handler`, có constructor public không tham số; đưa token của lớp đó qua `handlerClass` và tạo đối tượng.
4. Thêm một lớp abstract triển khai `Handler`; kiểm tra nó qua được `asSubclass`, rồi tách riêng vấn đề khởi tạo.
5. So sánh `String.class.isInstance(null)` với `String.class.cast(null)` để giải thích khác biệt.
6. Thử token kiểu cha như `Number.class` với nhiều lớp số phù hợp để xác nhận phép kiểm tra dùng quan hệ gán được, không chỉ so sánh đúng bằng lớp.

Sau bài, cần phân biệt rõ **đối tượng đã có**, **kiểu được phát hiện** và **thao tác tạo đối tượng**. `cast` và `asSubclass` kiểm tra hai loại thông tin đầu tiên; chúng không thay cho chuyển dữ liệu hoặc logic khởi tạo.
