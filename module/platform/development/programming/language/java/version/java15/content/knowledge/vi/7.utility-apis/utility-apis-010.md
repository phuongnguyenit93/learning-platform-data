# Mô tả hằng số và sự khác biệt với chuyển đổi giá trị trong Java

> **Phạm vi:** Bài học thuộc nhóm **API tiện ích** trong module Java 15. Nội dung tập trung vào `describeConstable()`, `Constable`, `ConstantDesc` và sự khác biệt với các API **chuyển đổi giá trị** như `String.valueOf(...)`, `Integer.valueOf(...)`, `Integer.parseInt(...)`, `toString()`. Các API hằng số được trình bày đều đã chuẩn hóa và tiếp tục được dùng trên JDK 17, 21, 25 và các JDK hiện đại. Không cần chạy JDK 15 hay bật preview feature để học bài này.

## 1. Cần phân biệt hai câu hỏi khác nhau

Hãy đặt hai câu hỏi cho một giá trị Java, ví dụ số nguyên 42:

1. **Mô tả hằng số:** "Có thể biểu diễn giá trị này bằng một **mô tả hằng số danh nghĩa** (*nominal constant descriptor*) dùng trong mô hình constant pool của JVM hay không?"
2. **Chuyển đổi giá trị:** "Tôi muốn chuyển số 42 thành chuỗi `"42"`, hoặc chuyển chuỗi `"42"` thành số 42, bằng API nào?"

Hai câu hỏi có **mục đích và kiểu kết quả khác nhau**.

```java
Integer number = 42;

// Hỏi cách mô tả giá trị như một hằng số có thể nạp.
java.util.Optional<Integer> description = number.describeConstable();

// Chuyển số thành văn bản.
String text = String.valueOf(number);

// Phân tích văn bản để nhận số nguyên primitive.
int parsed = Integer.parseInt(text);
```

Ở đây:

- `description` là `Optional<Integer>`, thuộc cơ chế mô tả hằng số.
- `text` là `String` mang nội dung `"42"`.
- `parsed` là giá trị primitive `int` bằng 42.
- Dù vài giá trị trông giống nhau khi in, ý nghĩa API **không** giống nhau.

Đặc biệt, **`describeConstable()` không phải cách gọi khác của `toString()`, `String.valueOf()` hoặc `parseInt()`**. Nó không có nhiệm vụ biến một giá trị tùy ý thành văn bản cho người dùng hay phân tích văn bản thành một kiểu dữ liệu.

## 2. `Constable` và `ConstantDesc` là gì?

Các kiểu trung tâm nằm trong package `java.lang.constant` của Java:

| Thành phần | Vai trò | Ghi nhớ |
| --- | --- | --- |
| `Constable` | Interface dành cho loại giá trị có khả năng **tự mô tả bằng descriptor danh nghĩa** | Công bố phương thức `describeConstable()` |
| `ConstantDesc` | Interface đại diện cho **một mô tả hằng số có thể nạp** (loadable constant) | Có phương thức `resolveConstantDesc(MethodHandles.Lookup)` |
| `ClassDesc` | Mô tả danh nghĩa cho một kiểu `Class` | Có thể chứa dạng descriptor như `Ljava/lang/String;` |
| `MethodTypeDesc`, `MethodHandleDesc` | Mô tả danh nghĩa cho kiểu phương thức hoặc method handle | Hữu ích cho xử lý bytecode, liên kết động |
| `DynamicConstantDesc<T>` | Mô tả một hằng số động qua bootstrap method và các đối số | Ví dụ dùng để biểu diễn một số kiểu enum hoặc wrapper |
| `Optional` | Vỏ chứa kết quả nếu có descriptor | `Optional.empty()` nghĩa là không tạo được mô tả theo API |

Giao diện `Constable` công bố dạng tổng quát:

```java
Optional<? extends ConstantDesc> describeConstable();
```

Một số lớp hiện thực có **kiểu trả về cụ thể hơn**. Chẳng hạn `String` trả `Optional<String>`, còn `Class<?>` trả `Optional<ClassDesc>`. Chúng vẫn đáp ứng quy tắc tổng quát của `Constable`.

### "Mô tả danh nghĩa" nghĩa là gì?

`ConstantDesc` biểu diễn **thông tin đủ để mô tả hoặc, khi phù hợp, tìm lại giá trị hằng số trong ngữ cảnh nạp lớp**. Hãy xem nó như một **công thức hoặc ký hiệu liên kết** cho hệ thống xử lý classfile/bytecode:

- `ClassDesc` có thể mô tả lớp `java.lang.String` bằng descriptor `Ljava/lang/String;`.
- Khi cần, một descriptor có thể được **resolve** trong ngữ cảnh `MethodHandles.Lookup` để thu được giá trị tương ứng.
- Quá trình resolve có thể phụ thuộc vào **class loader, khả năng truy cập, tên lớp/phương thức và môi trường chạy**; không phải lúc nào cũng thành công.
- Descriptor **không mặc nhiên là một chuỗi để hiển thị**, cũng không có nghĩa dữ liệu được ghi ngay vào constant pool chỉ vì bạn gọi `describeConstable()`.

Đây là cơ sở cho các công cụ đọc/ghi bytecode, phân tích chương trình, xử lý lệnh `ldc`, constant pool và liên kết động. Đối với chương trình quản lý form, xử lý số hoặc in thông báo thông thường, các API chuyển đổi giá trị thường đúng nhu cầu hơn.

## 3. Vì sao `describeConstable()` trả về `Optional`?

Một kiểu `Constable` có thể mô tả được **một số instance nhưng không phải mọi instance**. Vì vậy:

```java
import java.lang.constant.Constable;
import java.lang.constant.ConstantDesc;
import java.util.Optional;

class DescriptorHelpers {
    static Optional<? extends ConstantDesc> describe(Constable value) {
        return value.describeConstable();
    }
}
```

Đoạn này là **một lớp tiện ích độc lập không có `main`**, chỉ minh họa đúng kiểu trả về khi gọi qua interface. Nó không giải mã, chuyển đổi hay in giá trị.

Ý nghĩa của kết quả:

- `Optional.of(descriptor)`: instance hiện tại **có thể cung cấp mô tả**.
- `Optional.empty()`: instance đó **không thể cung cấp mô tả** theo quy tắc của kiểu này. Không nên mặc định coi đó là lỗi lập trình.
- Gọi `get()` khi `Optional` rỗng gây `NoSuchElementException`; có thể dùng `isPresent()`, `ifPresent(...)` hoặc `orElseThrow()` khi đã xác định chắc chắn descriptor phải tồn tại.
- `Optional` không phải một cơ chế chuyển đổi kiểu. Kiểu bên trong vẫn là một dạng `ConstantDesc` cụ thể.

Ví dụ có thật: không phải mọi `MethodHandle` đều có mô tả danh nghĩa được hỗ trợ; những handle kết hợp bằng các combinator có thể không mô tả được như một direct method handle.

**Đừng nhầm `Optional.empty()` với `null`**: đây là một trạng thái hợp lệ được biểu diễn rõ qua API. Không thể gọi `null.describeConstable()`; lời gọi trên `null` sẽ dẫn tới `NullPointerException`.

## 4. Các kiểu descriptor điển hình vẫn dùng hiện nay

| Giá trị gốc | Lời gọi | Kiểu kết quả | Điểm đáng chú ý |
| --- | --- | --- | --- |
| `String`, ví dụ `"Java"` | `"Java".describeConstable()` | `Optional<String>` | Bản thân `String` vừa là giá trị vừa là `ConstantDesc` |
| `Integer`, ví dụ `Integer.valueOf(42)` | `number.describeConstable()` | `Optional<Integer>` | `Integer` tự mô tả bằng chính instance |
| `Long`, `Float`, `Double` | `value.describeConstable()` | `Optional<Long/Float/Double>` tương ứng | Những wrapper này cũng làm `ConstantDesc` |
| `Class<?>`, ví dụ `String.class` | `String.class.describeConstable()` | `Optional<ClassDesc>` | Descriptor tượng trưng cho **lớp**, không phải tên lớp hiển thị |
| `Enum`, ví dụ `Status.READY` | `Status.READY.describeConstable()` | `Optional<Enum.EnumDesc<Status>>` | Mô tả enum constant qua descriptor chuyên biệt, nếu tạo được |
| `Boolean`, `Byte`, `Short`, `Character` | `value.describeConstable()` | `Optional<DynamicConstantDesc<...>>` tương ứng | Dùng dạng mô tả động theo API, không nên ép mọi descriptor thành `String` |

Lưu ý cú pháp `Optional<Long/Float/Double>` trong bảng là **cách viết gộp để giải thích**, không phải mã Java generic hợp lệ. Mỗi lớp có kiểu riêng, như `Optional<Long>` và `Optional<Double>`.

**Với `String` và `Integer`:** việc gọi `describeConstable()` thường cho `Optional` chứa **chính instance đang có**. Vì vậy, khi in descriptor ra console, kết quả **có thể nhìn giống văn bản do `valueOf` tạo ra**, nhưng cơ chế API và kiểu trả về vẫn khác nhau.

**Với `Class` và `Enum`:** descriptor thường là một đối tượng mô tả chuyên biệt. Đây là lý do không được suy luận rằng `describeConstable()` luôn trả về "chuỗi biểu diễn" của giá trị.

## 5. Chương trình hoàn chỉnh: mô tả và resolve hằng số

Tạo tệp **`ConstantDescriptionDemo.java`** với nội dung sau. Ví dụ dùng Java 17+, các lớp `java.base` và các giá trị truy cập được trong chương trình.

```java
import java.lang.constant.ClassDesc;
import java.lang.invoke.MethodHandles;
import java.util.Optional;

public class ConstantDescriptionDemo {
    enum Status { READY, DONE }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        String text = "Java";
        Optional<String> textDesc = text.describeConstable();
        System.out.println("string.present=" + textDesc.isPresent());
        System.out.println("string.desc=" + textDesc.orElseThrow());

        Integer count = Integer.valueOf(42);
        Optional<Integer> intDesc = count.describeConstable();
        System.out.println("integer.present=" + intDesc.isPresent());
        System.out.println("integer.desc=" + intDesc.orElseThrow());

        ClassDesc classDesc =
                String.class.describeConstable().orElseThrow();
        System.out.println("class.desc="
                + classDesc.descriptorString());
        System.out.println("class.resolved="
                + (classDesc.resolveConstantDesc(MethodHandles.lookup())
                        == String.class));

        Optional<Enum.EnumDesc<Status>> statusDesc =
                Status.DONE.describeConstable();
        System.out.println("enum.present=" + statusDesc.isPresent());
        System.out.println("enum.name="
                + statusDesc.orElseThrow().constantName());
        System.out.println("enum.resolved="
                + (statusDesc.orElseThrow()
                        .resolveConstantDesc(MethodHandles.lookup())
                        == Status.DONE));
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 ConstantDescriptionDemo.java
java ConstantDescriptionDemo
```

**Stdout dự kiến trên JDK 17+:**

```text
string.present=true
string.desc=Java
integer.present=true
integer.desc=42
class.desc=Ljava/lang/String;
class.resolved=true
enum.present=true
enum.name=DONE
enum.resolved=true
```

Phân tích:

1. `text.describeConstable()` cho `Optional<String>` chứa `"Java"`. In `String` ấy ra console sẽ hiện `Java`, nhưng **không phát sinh bước chuyển String sang String**.
2. `count.describeConstable()` cho `Optional<Integer>` chứa giá trị Integer 42. `println` **tự định dạng** Integer khi in, nên màn hình cũng hiện `42`; đây **không** phải giá trị String do `describeConstable` trả về.
3. `String.class.describeConstable()` cho một `ClassDesc`, và `descriptorString()` trả về chuỗi descriptor của JVM: `Ljava/lang/String;`. Dạng này **khác** tên Java dễ đọc `java.lang.String`.
4. `classDesc.resolveConstantDesc(MethodHandles.lookup())` giải descriptor theo lookup hiện tại; với `String.class` công khai, kết quả là chính lớp `String`.
5. `Status.DONE.describeConstable()` cho `EnumDesc<Status>` trong ví dụ này. `constantName()` là `DONE`; resolve theo lookup của lớp chứa enum thu lại constant `Status.DONE`.

**Vì sao `throws ReflectiveOperationException`?** Việc resolve descriptor có thể cần nạp hoặc truy cập kiểu theo tên và có thể thất bại. Chữ ký API cho phép ném checked exception thuộc nhóm phản chiếu. Không nên tự ý gọi resolve trên các descriptor không rõ nguồn gốc chỉ để “xem nó là gì”.

## 6. Chuyển đổi giá trị: việc của `valueOf`, `parseInt`, `toString`

Bảng sau đặt các API cạnh nhau để tránh nhầm tên gọi:

| API | Đầu vào | Kết quả | Mục đích |
| --- | --- | --- | --- |
| `someConstable.describeConstable()` | Một instance hỗ trợ `Constable` | `Optional<? extends ConstantDesc>` hoặc kiểu `Optional` chuyên biệt | Nhận **mô tả danh nghĩa của hằng số**, nếu có |
| `someDesc.resolveConstantDesc(lookup)` | Descriptor và ngữ cảnh lookup | Giá trị được mô tả, hoặc lỗi khi resolve | Giải mô tả sang thực thể JVM |
| `String.valueOf(42)` | Giá trị số `int` | `String` `"42"` | Chuyển giá trị thành văn bản |
| `String.valueOf((Object) item)` | Đối tượng bất kỳ | `String` biểu diễn đối tượng (dùng `toString` của đối tượng nếu không null) | Hiển thị/ghi văn bản |
| `Integer.toString(42)` | `int` | `String` `"42"` | Đổi số nguyên thành chữ số thập phân |
| `Integer.parseInt("42")` | `String` hợp lệ | primitive `int` 42 | Phân tích văn bản thành số |
| `Integer.valueOf("42")` | `String` hợp lệ | `Integer` 42 | Phân tích và nhận wrapper object |
| `Integer.valueOf(42)` | primitive `int` | `Integer` 42 | Nhận wrapper object, có thể dùng cache nội bộ |
| `String.format("%04d", 7)` | Mẫu và đối số | `String` `"0007"` | Định dạng chuỗi theo quy tắc `Formatter` |
| `Enum.valueOf(Status.class, "DONE")` | Lớp enum và tên chính xác | `Status.DONE` | Tra cứu enum constant từ tên |

Cần nhớ `valueOf` **không có một ý nghĩa chung duy nhất** với mọi lớp. `String.valueOf` hướng tới kết quả **String**; `Integer.valueOf` hướng tới kết quả **Integer**; `Enum.valueOf` tìm một giá trị enum theo tên. Phải đọc **lớp sở hữu phương thức và kiểu tham số** để hiểu đúng.

### Ví dụ mất cách viết nguồn khi chuyển đổi

Giả sử dữ liệu bên ngoài có giá trị `"0042"`. Chuyển sang số làm mất **hai số 0 đầu**, bởi số nguyên 42 không giữ thông tin hình thức chữ số ban đầu.

Tạo **`ValueConversionDemo.java`**:

```java
public class ValueConversionDemo {
    public static void main(String[] args) {
        String raw = "0042";

        int parsed = Integer.parseInt(raw);
        Integer boxed = Integer.valueOf(raw);
        String reconstructed = String.valueOf(parsed);

        System.out.println("raw=" + raw);
        System.out.println("parsed=" + parsed);
        System.out.println("boxed=" + boxed);
        System.out.println("reconstructed=" + reconstructed);
        System.out.println("sameText=" + raw.equals(reconstructed));

        System.out.println("hasDescriptor="
                + raw.describeConstable().isPresent());
        System.out.println("describedText="
                + raw.describeConstable().orElseThrow());

        try {
            Integer.parseInt("four");
        } catch (NumberFormatException ex) {
            System.out.println("invalidNumber=true");
        }
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 ValueConversionDemo.java
java ValueConversionDemo
```

**Stdout chính xác:**

```text
raw=0042
parsed=42
boxed=42
reconstructed=42
sameText=false
hasDescriptor=true
describedText=0042
invalidNumber=true
```

Giải thích:

- `parseInt("0042")` phân tích thành số `int` 42. `Integer.valueOf("0042")` phân tích và trả wrapper `Integer` 42.
- `String.valueOf(parsed)` xây dựng văn bản từ **giá trị số**, nên thành `"42"`; không biết trước đó chuỗi chứa hai số 0 đầu.
- `raw.describeConstable()` mô tả **chính String `"0042"`**; với `String`, mô tả là bản thân chuỗi và vẫn có hai số 0 đầu.
- `Integer.parseInt("four")` ném `NumberFormatException`; đây là **lỗi chuyển đổi chuỗi thành số**, không liên quan đến `Optional.empty()` của `Constable`.

Nếu bạn xử lý **mã học viên, mã bưu chính, mã hóa đơn** có số 0 đầu mang ý nghĩa, hãy giữ kiểu `String` và **không tự động dùng `parseInt`** chỉ vì ký tự đều là chữ số.

## 7. Một `String` làm descriptor của chính nó có phải chuyển kiểu không?

Không. Theo API hiện hành, `String` và `Integer` đều hiện thực **cả `Constable` lẫn `ConstantDesc`**. Điều đó cho phép chúng đóng vai trò **giá trị** và **mô tả danh nghĩa của giá trị đó** trong cơ chế JVM.

```java
String s = "hello";
String desc = s.describeConstable().orElseThrow();
boolean sameText = s.equals(desc);
```

`sameText` là `true`. Thế nhưng kết luận đúng là "`describeConstable` cung cấp mô tả thành công; ở kiểu `String`, mô tả là chính chuỗi đó". Không nên nói "nó đã chuyển `String` sang một kiểu descriptor mới có văn bản giống hệt".

So sánh:

```java
String original = "0042";
String descriptor = original.describeConstable().orElseThrow();
int numeric = Integer.parseInt(original);
String converted = String.valueOf(numeric);
```

- `descriptor` còn là `"0042"`, vì mô tả hằng số của `String` này giữ nguyên giá trị nguồn.
- `numeric` là `int` 42.
- `converted` là `"42"`, phản ánh giá trị số đã phân tích.

Đó là một cách trực quan để thấy **mô tả hằng số** và **chuyển đổi giá trị** thuộc hai loại hành vi khác nhau.

### `ConstantDesc` và việc giải mô tả

Một `ConstantDesc` có phương thức:

```java
Object resolveConstantDesc(
        java.lang.invoke.MethodHandles.Lookup lookup)
        throws ReflectiveOperationException;
```

Đây là chữ ký **khái quát theo interface**; các kiểu con có thể khai báo kiểu trả về cụ thể hơn.

- Với `String`, `Integer` và một số giá trị tĩnh tương tự, lời giải descriptor về cơ bản trả lại giá trị được mô tả.
- Với `ClassDesc`, kết quả liên quan đến kiểu `Class<?>` trong ngữ cảnh nạp lớp và quyền truy cập.
- Với `EnumDesc` hoặc dynamic constants, việc giải descriptor có thể dựa vào bootstrap method và thông tin lớp liên quan.
- Việc có descriptor **không đảm bảo** resolve luôn thành công trong **mọi** class loader hoặc môi trường khác nhau.

Hãy coi `resolveConstantDesc` là thao tác của **API mô hình JVM**, không phải phương thức parse dữ liệu người dùng.

## 8. "Hằng số" ở đây không đồng nghĩa với từ khóa `final`

Trong Java, từ **hằng số** xuất hiện ở nhiều ngữ cảnh:

- `final int count = 10;`: biến không thể được **gán lại** sau khi khởi tạo đúng quy tắc của ngôn ngữ. Trường hợp cụ thể có thể là *constant variable* theo JLS nếu thỏa kiểu và constant expression.
- `static final int LIMIT = 10;`: mẫu khai báo hằng số số học quen thuộc; vẫn phải phân biệt những trường hợp không thỏa điều kiện constant expression.
- `Constable` / `ConstantDesc`: API **mô tả hằng số nạp được của JVM**. Khả năng tạo descriptor không phải một cách khai báo biến `final`, không biến mọi instance thành bất biến, cũng không phải cơ chế lưu dữ liệu lâu dài.

```java
final String name = "Java";
String other = String.valueOf(123);
boolean canDescribe = name.describeConstable().isPresent();
```

`final` chỉ nói tới **ràng buộc gán lại** của biến `name`. Việc `name` có thể tạo descriptor là nhờ **kiểu và instance `String`**, không phải vì từ khóa `final`.

Ngược lại, một instance `String` **không được lưu trong biến `final`** vẫn có `describeConstable()`:

```java
String current = "first";
current = "second";
boolean present = current.describeConstable().isPresent();
```

Giá trị `present` là `true`, vì giá trị String hiện tại vẫn có thể tự mô tả.

## 9. Khi nào nên dùng API nào?

**Đọc/ghi classfile hoặc phát sinh bytecode:** dùng `ClassDesc`, `MethodTypeDesc`, `ConstantDesc` và các API liên quan khi cần biểu diễn toán hạng hằng số hoặc tên kiểu theo chuẩn JVM. `describeConstable()` có thể giúp thu descriptor từ instance hiện có.

**Hiển thị số lượng sản phẩm hoặc điểm số trên giao diện:** dùng `String.valueOf`, `String.format` hoặc API định dạng locale tương ứng. Đừng tạo descriptor chỉ để lấy chữ số rồi in.

**Nhận số từ form hoặc file CSV:** dùng `Integer.parseInt` hoặc `Integer.valueOf`, kiểm tra định dạng đầu vào và xử lý `NumberFormatException`. Đây là một bước phân tích dữ liệu thực sự.

**Tìm giá trị enum từ văn bản tin cậy:** dùng `Enum.valueOf(Status.class, "DONE")` hoặc `Status.valueOf("DONE")`, với tên chính xác và xử lý lỗi nếu không tồn tại. `Enum.EnumDesc` phục vụ mô tả danh nghĩa; nó không thay thế API chuyển tên người dùng thành enum theo nhu cầu thông thường.

**Muốn biết một instance có thể được mô tả hay không:** dùng `describeConstable()` và kiểm tra `Optional`:

```java
import java.lang.constant.Constable;
import java.lang.constant.ConstantDesc;
import java.util.Optional;

class DescribeCheck {
    static boolean hasDescription(Constable value) {
        Optional<? extends ConstantDesc> result =
                value.describeConstable();
        return result.isPresent();
    }
}
```

Đây là lớp **minh họa không có `main`**. Phương thức không cần tự ép kiểu kết quả sang `String` hay `Integer`. Nếu cần dùng descriptor, hãy kiểm tra kiểu cụ thể và mục tiêu xử lý thay vì gọi `toString()` rồi suy đoán nội dung.

## 10. Các lỗi hay gặp

| Sai lầm | Hậu quả | Cách hiểu/cách sửa |
| --- | --- | --- |
| Cho rằng `describeConstable()` trả chuỗi để in | Kiểu trả về thường là `Optional` chứa một descriptor | Dùng `String.valueOf`/`toString` nếu mục đích là biểu diễn văn bản |
| Cho rằng `describeConstable()` parse một `String` thành số | `"0042".describeConstable()` vẫn mô tả **String `"0042"`** | Dùng `Integer.parseInt`/`Integer.valueOf` để phân tích số |
| Khẳng định mọi `Constable` luôn có descriptor | Một số instance có thể trả `Optional.empty()` | Kiểm tra `isPresent` hoặc xử lý nhánh rỗng |
| Gọi `optional.get()` khi chưa biết trạng thái | Có thể ném `NoSuchElementException` | Dùng `ifPresent`, `map`, `orElseThrow` trong trường hợp phù hợp |
| Ép mọi `ConstantDesc` sang `String` | `ClassDesc`, `EnumDesc` và nhiều loại khác không phải `String` | Tôn trọng kiểu descriptor cụ thể hoặc dùng interface tổng quát |
| Tưởng `final` làm mọi đối tượng trở thành `Constable` | `final` nói về gán lại, không nói về khả năng mô tả JVM constant | Xem kiểu có hiện thực `Constable` và instance có descriptor hay không |
| Dùng `==` để so sánh hai wrapper có cùng số | Có thể phụ thuộc identity/cache thay vì bằng nhau về giá trị | Dùng `equals` cho đối tượng hoặc unbox có chủ đích |
| Dùng `Integer.parseInt` cho mã có số 0 đầu | Mất cách viết ban đầu của mã | Giữ `String` nếu số 0 đầu có ý nghĩa |
| Gọi resolve với descriptor tùy ý và giả định luôn thành công | Có thể thất bại vì tên lớp, class loader hoặc quyền truy cập | Kiểm soát nguồn descriptor, dùng `Lookup` phù hợp và xử lý lỗi |
| Dùng `toString` của descriptor làm định dạng lưu trữ bền vững | Không phải mọi `toString` đều là serialization contract | Dùng API cấu trúc chính thức và giao thức lưu trữ được quy định |

### Ngoại lệ và cách xử lý thực tế

- `NumberFormatException`: văn bản không thể được phân tích thành số hợp lệ, ví dụ `Integer.parseInt("abc")`.
- `IllegalArgumentException`: có thể xuất hiện với tên enum không tồn tại khi dùng `valueOf`, hoặc đầu vào descriptor không hợp lệ khi tạo mô tả.
- `ReflectiveOperationException`: có thể xuất hiện trong quá trình `resolveConstantDesc` vì không thể giải quyết một phần mô tả theo ngữ cảnh lookup.
- `NoSuchElementException`: có thể phát sinh nếu lấy giá trị từ `Optional` rỗng mà không xử lý trạng thái.

Đừng tự động bắt mọi exception rồi in `null`: mỗi tình huống phản ánh **hợp đồng API khác nhau** và nên có phương án báo lỗi hoặc xử lý phù hợp.

## 11. Bài tập thực hành có đáp án

**Bài 1.** Với `String raw = "0009";`, hãy dự đoán kết quả:

```java
String raw = "0009";
System.out.println(raw.describeConstable().orElseThrow());
System.out.println(String.valueOf(Integer.parseInt(raw)));
```

**Đáp án:**

```text
0009
9
```

Dòng đầu mô tả String giữ nguyên; dòng sau parse thành số rồi chuyển lại thành văn bản nên mất các số 0 đầu.

**Bài 2.** `String.class.describeConstable()` trả về `Optional<String>` hay `Optional<ClassDesc>`?

**Đáp án:** `Optional<ClassDesc>`. Descriptor mô tả **kiểu lớp `String`**, không phải một instance String chứa văn bản.

**Bài 3.** Tại sao không thể mặc định `someConstable.describeConstable().get()` luôn thành công?

**Đáp án:** `Constable` cho phép `Optional.empty()` khi instance không thể tạo nominal descriptor. Cần xử lý trường hợp thiếu mô tả.

**Bài 4.** Đầu vào form là `"24"` và bạn cần làm phép cộng 1. Chọn API phù hợp nhất?

```java
int age = Integer.parseInt("24");
int next = age + 1; // 25
```

Dùng `parseInt` vì yêu cầu là chuyển văn bản thành số, không phải mô tả constant pool.

**Bài 5.** `Integer.valueOf("17")` và `String.valueOf(17)` trả về cùng kiểu không?

**Đáp án:** Không. Dòng đầu trả `Integer` (giá trị số dạng wrapper), dòng sau trả `String` (văn bản `"17"`).

**Bài 6.** `String.class.describeConstable().orElseThrow().descriptorString()` cho giá trị gì?

**Đáp án:** `Ljava/lang/String;`, là **descriptor kiểu trường của JVM**; `String.class.getName()` mới cho tên lớp dạng `java.lang.String`.

**Bài 7.** Khi nào cần gọi `resolveConstantDesc(MethodHandles.lookup())`?

**Đáp án:** Khi thật sự cần **giải một nominal descriptor thành giá trị hoặc thực thể JVM**, trong ngữ cảnh class loader và quyền truy cập thích hợp. Không dùng nó như bước thay thế `valueOf`, `parseInt` hay `toString`.

### Checklist

- [ ] Tôi giải thích được `Constable`, `ConstantDesc` và `describeConstable()`.
- [ ] Tôi biết `describeConstable()` trả `Optional` và đôi khi không có descriptor.
- [ ] Tôi biết tại sao `String`, `Integer` có thể là descriptor của chính mình.
- [ ] Tôi phân biệt `ClassDesc`, `EnumDesc` và các descriptor chuyên biệt.
- [ ] Tôi biết khi nào cần `resolveConstantDesc` và vai trò của `MethodHandles.Lookup`.
- [ ] Tôi dùng `String.valueOf`, `Integer.valueOf`, `parseInt` cho đúng kiểu đầu ra mong muốn.
- [ ] Tôi hiểu khác biệt giữa mô tả JVM constant, chuyển đổi kiểu và từ khóa `final`.
- [ ] Tôi không dùng `describeConstable()` như phương thức hiển thị hoặc parse dữ liệu.

## Tài liệu chính thức

1. [Java SE 25 — Package `java.lang.constant`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/constant/package-summary.html): mục đích, nominal descriptors và hệ thống `ConstantDesc`.
2. [Java SE 25 — Interface `Constable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/constant/Constable.html): `describeConstable()` và trường hợp `Optional.empty()`.
3. [Java SE 25 — Interface `ConstantDesc`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/constant/ConstantDesc.html): mô tả hằng số có thể nạp và `resolveConstantDesc`.
4. [Java SE 25 — `String` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `describeConstable`, `valueOf` và chuyển chuỗi.
5. [Java SE 25 — `Integer` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html): `describeConstable`, `parseInt`, `valueOf`.
6. [Java SE 25 — `ClassDesc` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/constant/ClassDesc.html): kiểu descriptor, `descriptorString` và resolve.
7. [JVM Specification 25, `4.4](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.4): cấu trúc constant pool trong class file.

**Kết luận:** `describeConstable()` trả về **mô tả hằng số danh nghĩa** nếu tạo được; nó thuộc hệ thống biểu diễn giá trị và liên kết của JVM. `valueOf(...)`, `parseInt(...)` và `toString()` phục vụ **chuyển đổi hoặc biểu diễn giá trị**. Hãy chọn API theo kiểu đầu vào, kiểu đầu ra và nhu cầu thực tế, thay vì chỉ nhìn tên “hằng số” hoặc “giá trị”.