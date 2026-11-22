# Giới hạn mô tả danh định qua describeConstable đối với hidden class (Java 15+)

## Mục tiêu bài học

**Hidden class** là một lớp được JVM tạo từ bytecode qua API `MethodHandles.Lookup.defineHiddenClass(...)`, chính thức từ **Java 15 (JEP 371)**. Nó có đối tượng `Class<?>` thật và có thể được sử dụng trong quá trình chạy, nhưng không có tên nhị phân (*binary name*) để những lớp khác tham chiếu theo cách thông thường.

Hệ quả quan trọng: với `Class<?>` đại diện cho hidden class, lời gọi **`describeConstable()` trả `Optional.empty()`**, vì Java không thể tạo một **mô tả danh định** (*nominal descriptor*) cho loại lớp này. Bài học tập trung vào chính giới hạn đó, phân biệt nó với việc lớp vẫn tồn tại và hoạt động tại runtime.

Sau bài này, bạn có thể:

1. Giải thích `Class.describeConstable()`, `ClassDesc`, `Optional<ClassDesc>` và khái niệm mô tả danh định.
2. Dự đoán kết quả cho lớp thường, hidden class và **mảng có phần tử là hidden class**.
3. Phân biệt `Class.descriptorString()` với một *field descriptor* hợp lệ mà `ClassDesc.ofDescriptor(...)` chấp nhận.
4. Tạo hidden class thực tế bằng `Lookup.defineHiddenClass`, chứng minh không thể tìm lại nó qua tên nhưng vẫn gọi được phương thức bằng `MethodHandle`.
5. Thiết kế mã xử lý trường hợp `Optional.empty()` mà không giả định mọi `Class<?>` đều có descriptor danh định.

**Phiên bản:** `Class.describeConstable()` là API từ Java 12; `Class.isHidden()` và `Lookup.defineHiddenClass` có từ Java 15. Những hành vi cốt lõi trình bày ở đây tiếp tục có hiệu lực trên JDK hiện đại. Chương trình được viết để **biên dịch với `--release 17`**, không dùng preview hay API legacy.

## 1. Mô tả danh định là gì?

Có hai cách khác nhau để nói về một lớp:

- **Đối tượng lớp lúc chạy:** `Class<?>` là đối tượng JVM đang giữ, đại diện cho một kiểu đã được nạp hoặc định nghĩa. Nó có thể được truyền vào reflection hoặc method handles.
- **Mô tả danh định:** `ClassDesc` thuộc `java.lang.constant` diễn tả một kiểu bằng **thông tin tên/ký hiệu**, để có thể thử giải quyết (*resolve*) trong một ngữ cảnh lookup phù hợp. Descriptor này không phải chính đối tượng `Class<?>` của một class loader cụ thể.

Ví dụ lớp thường:

```java
import java.lang.constant.ClassDesc;
import java.util.Optional;

Optional<ClassDesc> descriptor = String.class.describeConstable();

System.out.println(descriptor.isPresent());                // true
System.out.println(descriptor.orElseThrow().descriptorString()
        .equals("Ljava/lang/String;"));                    // true
```

Trong ví dụ, `Ljava/lang/String;` là một **field type descriptor** hợp lệ trong ký pháp của JVM. `ClassDesc` có thể mô tả ký hiệu `java.lang.String`; với quyền truy cập và class loader thích hợp, ký hiệu đó có thể được giải quyết thành một `Class<?>`.

Một `ClassDesc` **không tự giữ tham chiếu đến một instance `Class<?>` cụ thể**. Hai class loader có thể định nghĩa những lớp khác nhau với cùng tên nhị phân; vì vậy mô tả danh định không thay thế mọi thông tin định danh lớp ở runtime.

### 1.1. Hợp đồng của `Class.describeConstable()`

Chữ ký:

```java
public Optional<ClassDesc> describeConstable()
```

- Khi **có thể tạo** một mô tả danh định, `Optional` chứa `ClassDesc`.
- Khi **không thể tạo**, kết quả là `Optional.empty()`.
- API **không cam kết mọi đối tượng `Class<?>` đều cho kết quả có giá trị**. Vì thế không nên gọi `.get()` hoặc `.orElseThrow()` một cách mù quáng.
- Việc nhận `Optional.empty()` **không đồng nghĩa đối tượng `Class<?>` là null, chưa nạp hoặc không tồn tại**.

Điểm cuối đặc biệt quan trọng đối với hidden class: lớp đang tồn tại và có thể được thực thi; chỉ riêng việc tạo **biểu diễn danh định** của nó là không khả thi.

## 2. Vì sao hidden class không mô tả được bằng tên danh định?

Với một lớp thường như `java.lang.String`, Java có tên nhị phân xác định và có thể biểu diễn bằng `Ljava/lang/String;`. Hidden class lại do JVM định nghĩa với **tên không phải binary name**. Tên lúc chạy thường có hậu tố duy nhất được JVM bổ sung, ví dụ có dạng tương tự:

```text
HiddenTemplate/0x0000000000000000
```

Dòng trên **chỉ minh họa dạng tên**, không phải tên thật hay hậu tố bảo đảm xuất hiện nguyên văn; mỗi lần định nghĩa có thể khác nhau. Không nên lưu, phân tích cú pháp hậu tố hoặc so sánh tên hidden class với chuỗi cố định.

Hệ quả theo đặc tả của `java.lang.Class`:

- Hidden class **không thể tham chiếu danh định** từ constant pool của lớp khác theo cách một lớp có binary name được tham chiếu.
- `Class.forName(hidden.getName())` không tìm được hidden class chỉ nhờ chuỗi tên đó.
- `ClassDesc.of(...)` hoặc `ClassDesc.ofDescriptor(...)` **không thể dựng descriptor danh định trỏ đúng tới hidden class**.
- `hidden.describeConstable()` phải là `Optional.empty()`.

Đây là **giới hạn của tên và cơ chế mô tả ký hiệu**, không phải khẳng định hidden class là cơ chế bảo mật giúp mọi đối tượng khác không thể tương tác với nó. Nếu code đã giữ `Class<?>` hoặc `Lookup`/`MethodHandle` phù hợp, nó vẫn có thể làm việc với lớp.

## 3. Bảng đối chiếu: loại Class và describeConstable

| Đối tượng `Class<?>` | `isHidden()` | `describeConstable().isPresent()` | Ý nghĩa |
| --- | --- | --- | --- |
| `String.class` | `false` | `true` | Có binary name, mô tả danh định được |
| `int.class` | `false` | `true` | Kiểu nguyên thủy có descriptor JVM |
| `String[].class` | `false` | `true` | Mảng có kiểu phần tử mô tả danh định được |
| `HiddenTemplate.class` (lớp thường trước khi định nghĩa hidden class) | `false` | `true` | Lớp có tên nhị phân thông thường |
| `hidden` do `defineHiddenClass` tạo | `true` | `false` | Không có mô tả danh định |
| `hidden.arrayType()` | `false` | `false` | **Mảng không phải hidden class**, nhưng phần tử hidden khiến cả kiểu mảng không mô tả danh định được |

Dòng cuối là bẫy quan trọng. Java có thể tạo một **array class có phần tử là hidden class**, dù bản thân array class không mang trạng thái `isHidden() == true`. Vì không có descriptor danh định cho phần tử hidden, Java cũng không thể tạo mô tả danh định cho kiểu mảng ấy.

Do đó, **không dùng điều kiện `!clazz.isHidden()` làm bằng chứng chắc chắn rằng `clazz.describeConstable()` có giá trị**. Chính `Optional` trả về mới là câu trả lời của API.

## 4. Đừng nhầm `descriptorString()` với một descriptor danh định hợp lệ

`Class<?>` có phương thức `descriptorString()`. Với lớp thường:

```java
String descriptor = String.class.descriptorString();
// "Ljava/lang/String;"
```

Chuỗi đó được `ClassDesc.ofDescriptor(descriptor)` chấp nhận. Tuy nhiên, đối với một hidden class, `hidden.descriptorString()` **vẫn trả về một chuỗi**, nhưng theo tài liệu `Class`, chuỗi này **không phải field type descriptor hợp lệ** và không thể biến thành `ClassDesc` danh định.

Ví dụ sau chỉ mô tả thao tác xảy ra sau khi có biến `hidden`:

```java
String text = hidden.descriptorString(); // Có giá trị chuỗi.
ClassDesc.ofDescriptor(text);            // IllegalArgumentException
```

Dòng thứ hai **dự kiến ném exception**, không phải cách dựng descriptor dùng được. Ví dụ chương trình đầy đủ ở dưới bắt đúng exception và tiếp tục chạy.

Điều tương tự áp dụng cho `hidden.arrayType().descriptorString()`: chuỗi có thể nhận được, nhưng vì kiểu phần tử là hidden class, nó **không tạo được nominal `ClassDesc` cho mảng đó**.

### 4.1. Vì sao không sửa chuỗi tên hoặc lắp `ClassDesc.of(...)` thủ công?

`ClassDesc.of("HiddenTemplate")` biểu diễn **lớp thường** có binary name `HiddenTemplate`, không biểu diễn hidden class mà JVM đã sinh từ cùng bytecode. Nó không thể được “nâng cấp” bằng cách thêm hậu tố `/0x...` hoặc thay một vài ký tự trong `descriptorString()`.

Một `ClassDesc` có thể được tạo từ tên hợp lệ **ngay cả khi lớp có tên đó không tồn tại** trong môi trường giải quyết sau này. Bản thân việc tạo descriptor thành công không chứng minh nó trỏ tới đúng runtime class, càng không làm xuất hiện lại một hidden class đã được JVM định nghĩa trước đó.

## 5. Thí nghiệm chạy thật: defineHiddenClass rồi gọi describeConstable

Để minh họa đúng Java 15+ mà không phải viết bytecode thủ công hoặc cài thư viện bên ngoài, ta tạo **hai lớp trong cùng một tệp nguồn**:

- `HiddenConstableDemo` là lớp có `main`.
- `HiddenTemplate` là lớp thường, package-private, có phương thức tĩnh `answer()` trả `42`.

Sau khi biên dịch, `javac` tạo `HiddenTemplate.class` bên cạnh tệp class chính. Chương trình đọc các byte này và gọi:

```java
MethodHandles.lookup().defineHiddenClass(bytes, true)
```

Đối số `true` yêu cầu khởi tạo hidden class. API trả về một `Lookup` có lookup class là hidden class mới; từ đó gọi `lookupClass()` để lấy `Class<?>` của nó. Class file đầu vào phải đáp ứng các yêu cầu về package và quyền truy cập của `Lookup`. Trong ví dụ, hai lớp nằm cùng **unnamed package**, nên có thể dùng lookup của chương trình chính; một dự án có package cần tổ chức các lớp đúng package tương ứng.

### 5.1. Chương trình hoàn chỉnh

Lưu nội dung sau vào tệp **`HiddenConstableDemo.java`** bằng UTF-8:

```java
import java.io.InputStream;
import java.lang.constant.ClassDesc;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class HiddenConstableDemo {
    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream stream =
                     HiddenTemplate.class.getResourceAsStream("HiddenTemplate.class")) {
            if (stream == null) {
                throw new IllegalStateException("Missing HiddenTemplate.class");
            }
            bytes = stream.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, true);
        Class<?> hidden = hiddenLookup.lookupClass();
        Class<?> hiddenArray = hidden.arrayType();

        System.out.println("ordinaryNominal="
                + HiddenTemplate.class.describeConstable().isPresent());
        System.out.println("stringNominal="
                + String.class.describeConstable().isPresent());
        System.out.println("primitiveNominal="
                + int.class.describeConstable().isPresent());
        System.out.println("ordinaryArrayNominal="
                + String[].class.describeConstable().isPresent());
        System.out.println("isHidden=" + hidden.isHidden());
        System.out.println("hiddenNominal="
                + hidden.describeConstable().isPresent());
        System.out.println("arrayIsHidden=" + hiddenArray.isHidden());
        System.out.println("hiddenArrayNominal="
                + hiddenArray.describeConstable().isPresent());
        System.out.println("nameHasSlash=" + hidden.getName().contains("/"));

        boolean invalidDescriptor = false;
        try {
            ClassDesc.ofDescriptor(hidden.descriptorString());
        } catch (IllegalArgumentException expected) {
            invalidDescriptor = true;
        }
        System.out.println("hiddenDescriptorRejected=" + invalidDescriptor);

        boolean notLoadableByName = false;
        try {
            Class.forName(hidden.getName());
        } catch (ClassNotFoundException expected) {
            notLoadableByName = true;
        }
        System.out.println("notFoundByName=" + notLoadableByName);
        System.out.println("ordinaryStillNamed="
                + (Class.forName("HiddenTemplate") == HiddenTemplate.class));

        int result = (int) hiddenLookup.findStatic(
                hidden, "answer", MethodType.methodType(int.class)).invokeExact();
        System.out.println("invocable=" + (result == 42));
    }
}

class HiddenTemplate {
    public static int answer() {
        return 42;
    }
}
```

Chạy từ thư mục chứa `HiddenConstableDemo.java`, dùng **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 HiddenConstableDemo.java
java HiddenConstableDemo
```

Cần giữ tệp `HiddenTemplate.class` sau khi biên dịch vì chương trình đọc bytecode của nó làm đầu vào cho `defineHiddenClass`. Nếu chạy trong môi trường đóng gói, cách tải resource phải phản ánh cách tệp class được đưa vào classpath/module thực tế.

**Stdout chính xác của chương trình:**

```text
ordinaryNominal=true
stringNominal=true
primitiveNominal=true
ordinaryArrayNominal=true
isHidden=true
hiddenNominal=false
arrayIsHidden=false
hiddenArrayNominal=false
nameHasSlash=true
hiddenDescriptorRejected=true
notFoundByName=true
ordinaryStillNamed=true
invocable=true
```

Diễn giải từng nhóm:

- Bốn dòng đầu xác nhận mô tả danh định có thể tạo cho lớp thường, `String`, `int` và mảng lớp thường.
- `isHidden=true` và `hiddenNominal=false` xác nhận hidden class tồn tại nhưng `describeConstable()` không mô tả được nó.
- `arrayIsHidden=false` đi cùng `hiddenArrayNominal=false` cho thấy tính chất “không mô tả được” còn lan sang **kiểu mảng** chứa hidden element, dù mảng không tự là hidden class.
- `nameHasSlash=true` cho thấy tên do JVM gắn cho hidden class không phải binary name thường dùng. Kiểm tra này **không giả định hậu tố cụ thể**.
- `hiddenDescriptorRejected=true` xác nhận không thể lấy `descriptorString()` của hidden class rồi coi là descriptor hợp lệ để khởi tạo `ClassDesc`.
- `notFoundByName=true` và `ordinaryStillNamed=true` phân biệt hidden class với lớp thường có bytecode ban đầu: lớp thường còn tra được theo binary name, hidden class không.
- `invocable=true` chứng minh vẫn có thể gọi phương thức `answer()` bằng `MethodHandle` thông qua `Lookup` được trả về; thiếu mô tả danh định **không làm lớp trở nên không thể sử dụng**.

Không in trực tiếp tên hidden class ra phần stdout mong đợi: nó có phần hậu tố phát sinh trong quá trình chạy nên không phù hợp để kiểm thử so khớp chuỗi cố định.

## 6. `Optional.empty()` phải được xử lý như một trường hợp hợp lệ

Lỗi phổ biến là nghĩ hễ có `Class<?>` thì luôn có thể ép nó thành `ClassDesc`:

```java
// Dễ lỗi nếu type là hidden class hoặc loại không mô tả danh định được.
ClassDesc desc = type.describeConstable().orElseThrow();
```

Cú pháp trên hợp lệ khi `type` được khai báo là `Class<?>` và có descriptor; riêng hidden class nó ném `NoSuchElementException`. Nếu nhiệm vụ của bạn **bắt buộc phải có descriptor danh định**, việc từ chối đầu vào không mô tả được là đúng, nhưng cần báo lỗi rõ ràng:

```java
ClassDesc desc = type.describeConstable().orElseThrow(
        () -> new IllegalArgumentException(
                "Type has no nominal descriptor: " + type.getTypeName()));
```

Nếu descriptor chỉ phục vụ logging, báo cáo hoặc tối ưu hóa và **không bắt buộc**, nên giữ luồng fallback:

```java
String description = type.describeConstable()
        .map(ClassDesc::descriptorString)
        .orElse("<runtime-only / no nominal descriptor>");
```

Hai đoạn trên là **mã minh họa bên trong phương thức** đã có biến `Class<?> type` và import `java.lang.constant.ClassDesc`, không phải hai chương trình độc lập.

Trong thiết kế framework, lựa chọn xử lý tùy mục tiêu:

- Cần **định danh ký hiệu lưu trữ dài hạn**: yêu cầu một loại có descriptor, hoặc lưu một định danh ứng dụng do bạn quản lý, nhưng đừng giả định tên runtime của hidden class có thể dùng để tải lại cùng lớp.
- Cần **gọi phương thức lúc chạy**: tiếp tục truyền `Class<?>`, `Lookup` hoặc `MethodHandle` phù hợp trong bối cảnh runtime đang còn sử dụng được.
- Cần **tạo schema hoặc metadata**: phân biệt “có thể mô tả danh định” và “chỉ dùng được qua đối tượng/runtime handle”; trả lỗi có lý do hoặc dùng biểu diễn nội bộ không tuyên bố khả năng resolve bằng tên.

### 6.1. Kiểm thử theo hợp đồng thay vì bắt message exception

Một kiểm thử ổn định nên dùng:

```java
boolean cannotDescribe = hidden.describeConstable().isEmpty();
boolean canDescribeOrdinary = String.class.describeConstable().isPresent();
```

Với lời gọi `ClassDesc.ofDescriptor(hidden.descriptorString())`, có thể kiểm tra rằng nó ném `IllegalArgumentException`, không cần khớp **message** của exception vốn có thể khác giữa các phiên bản JDK.

Nếu kiểm thử tên, so sánh **tính chất** thay vì toàn bộ tên sinh ngẫu nhiên; ví dụ `hidden.isHidden()` hoặc khả năng `Class.forName` không tìm được hidden class.

## 7. Phân biệt bốn thao tác dễ nhầm

| API | Nó làm gì? | Kết quả với hidden class |
| --- | --- | --- |
| `hidden.isHidden()` | Hỏi lớp đang đại diện có phải hidden class không | `true` |
| `hidden.getName()` | Trả tên lớp lúc chạy dạng `String` | Có chuỗi tên không phải binary name |
| `hidden.descriptorString()` | Trả chuỗi mô tả theo quy tắc `Class` | Có chuỗi, **nhưng không phải field descriptor hợp lệ** |
| `hidden.describeConstable()` | Cố tạo `ClassDesc` danh định | `Optional.empty()` |
| `Class.forName(hidden.getName())` | Cố tìm lớp bằng binary name | `ClassNotFoundException` |
| `ClassDesc.ofDescriptor(hidden.descriptorString())` | Cố parse chuỗi thành descriptor danh định | `IllegalArgumentException` |
| `hiddenLookup.findStatic(...)` | Tạo method handle với quyền lookup phù hợp | Có thể thành công và gọi được phương thức |

Không có mâu thuẫn giữa việc `descriptorString()` **trả `String`** và `describeConstable()` **trả empty**. Hai API phục vụ hợp đồng khác nhau; sự tồn tại của một chuỗi không chứng minh nó là descriptor danh định hợp lệ.

### 7.1. Dễ nhầm hidden class với lớp ẩn sau giới hạn truy cập

Một lớp `private` hoặc `package-private` thông thường vẫn có binary name và có thể có `ClassDesc` danh định, dù không phải caller nào cũng được truy cập hay resolve nó. **Giới hạn truy cập** khác **không có tên nhị phân** của hidden class.

Tương tự, việc có `ClassDesc` không đồng nghĩa mọi `Lookup` đều giải quyết được nó: kết quả còn liên quan tới class loader, module và quyền truy cập. Ngược lại, việc thiếu `ClassDesc` không khiến một `MethodHandle` đang hoạt động trở thành vô hiệu chỉ vì lớp đích là hidden.

## 8. Những lựa chọn thiết kế thực tế

### 8.1. Công cụ sinh mã hoặc framework runtime

Trong những trường hợp framework tạo lớp phụ trợ khi chạy, hãy phân biệt:

- **Mục tiêu cần một lớp được tái tham chiếu bằng tên**: hidden class không đáp ứng hợp đồng đó. Nếu thành phần khác nhất định phải tìm lớp bằng binary name, cần chọn cơ chế thiết kế lớp **có tên phù hợp**.
- **Mục tiêu chỉ gọi hành vi trong cùng runtime**: giữ lookup/handle hoặc đối tượng lớp thích hợp, không cố serialize một tên hidden class rồi gọi `Class.forName` ở lần chạy sau.
- **Mục tiêu xuất descriptor vào metadata**: gọi `describeConstable()` và xử lý `Optional.empty()` như nhánh thiết kế bình thường, không coi là JVM lỗi.

Không nên suy đoán mọi lớp do thư viện động tạo đều là hidden class. Dùng `clazz.isHidden()` nếu cần kiểm tra thực tế; implementation detail của thư viện có thể đổi giữa các phiên bản.

### 8.2. Lưu trữ, cache và tương thích giữa các lần chạy

Giá trị `hidden.getName()` không phải **định danh bền vững để tái tạo lớp**. Nếu ứng dụng cần lưu lại thông tin nghiệp vụ, hãy lưu **định danh nghiệp vụ** hoặc cấu hình có thể tái tạo logic, không dùng chuỗi tên hidden class làm khóa để nạp lại đúng `Class<?>` sau khi restart.

Một `ClassDesc` của lớp thường cũng không lưu đầy đủ identity của class loader. Do đó, ngay cả trong trường hợp có nominal descriptor, vẫn phải suy xét ngữ cảnh resolve. Điều này không phải ngoại lệ của hidden class mà là giới hạn chung của việc mô tả bằng tên.

### 8.3. Không dùng hidden class để che giấu lỗ hổng bảo mật

Hidden class giúp thiết kế các thành phần runtime không cần tên nhị phân công khai; nó không phải một cơ chế *sandbox* hoặc hàng rào truy cập thay cho các quy tắc bảo mật, module và capability. Chương trình mẫu đã chủ động dùng `Lookup` để gọi thành công phương thức trên hidden class.

## 9. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gọi `hidden.describeConstable().get()` | `Optional` rỗng đối với hidden class | Dùng `isPresent`/`isEmpty`, `orElse` hoặc nhánh lỗi rõ ràng |
| Nghĩ `Class<?>` tồn tại thì descriptor phải tồn tại | Đối tượng runtime khác mô tả danh định | Dựa vào kết quả `describeConstable()` |
| Dùng `!clazz.isHidden()` để suy ra `describeConstable().isPresent()` | Mảng của hidden class có `isHidden=false` nhưng descriptor rỗng | Kiểm tra `Optional` thực sự |
| Dùng `ClassDesc.ofDescriptor(hidden.descriptorString())` | Chuỗi descriptor của hidden class không phải field descriptor hợp lệ | Không ép; dùng runtime `Class<?>`/`Lookup` nếu cần |
| Gọi `Class.forName(hidden.getName())` để tìm lớp đã tạo | Tên hidden class không phải binary name | Giữ tham chiếu runtime hoặc thiết kế cơ chế lớp có tên |
| Lưu hậu tố `/0x...` rồi mong nạp lại ở lần chạy khác | Tên phát sinh trong runtime, không phải định danh bền | Lưu định danh nghiệp vụ hoặc cấu hình tạo lớp |
| Cho rằng thiếu `ClassDesc` nghĩa là không thể gọi phương thức | `MethodHandle` và `Lookup` có thể làm việc với `Class<?>` thực | Tách khả năng “mô tả theo tên” khỏi “thực thi” |
| Hardcode toàn bộ `getName()` trong unit test | Hậu tố sinh ra có thể thay đổi | Kiểm tra `isHidden`, `Optional.empty` hoặc thuộc tính ổn định |
| Nhầm class `HiddenTemplate` với hidden class định nghĩa từ bytecode của nó | Hai `Class<?>` khác nhau dù bytecode cùng xuất phát từ một file | Đối chiếu `Class<?>` trả về từ `hiddenLookup.lookupClass()` |
| Định nghĩa hidden class từ package sai hoặc thiếu quyền lookup | `defineHiddenClass` kiểm tra package và quyền truy cập | Đặt bytecode cùng runtime package, dùng lookup hợp lệ, xử lý exception thật |

## 10. Bài tập tự kiểm tra

**Bài 1.** `Class<?> hidden` được tạo bằng `Lookup.defineHiddenClass`. `hidden.isHidden()` là `true`. Vậy `hidden.describeConstable().isPresent()` có giá trị gì?

**Đáp án:** `false`. Nó trả `Optional.empty()` vì không có nominal descriptor cho hidden class.

**Bài 2.** Nếu `Class<?> arrayType = hidden.arrayType();`, hãy dự đoán hai biểu thức:

```java
arrayType.isHidden();
arrayType.describeConstable().isPresent();
```

**Đáp án:** Cả hai đều là `false`. Array class **không phải hidden class**, nhưng kiểu mảng có phần tử hidden cũng không thể mô tả danh định.

**Bài 3.** `hidden.descriptorString()` trả về một chuỗi không rỗng. Có thể lấy chuỗi đó rồi tạo `ClassDesc` tương ứng bằng `ClassDesc.ofDescriptor(...)` hay không?

**Đáp án:** Không. Đó không phải descriptor hợp lệ theo cú pháp field type descriptor của JVM đối với hidden class; ví dụ kiểm thử xác nhận `IllegalArgumentException`.

**Bài 4.** Vì sao chương trình có thể gọi `hiddenLookup.findStatic(hidden, ...)` trong khi không gọi được `Class.forName(hidden.getName())`?

**Đáp án:** `Lookup` giữ quyền/ngữ cảnh và tham chiếu tới `Class<?>` thật trong runtime; `Class.forName` lại dùng tên nhị phân để tìm lớp, điều hidden class không cung cấp.

**Bài 5.** Một hàm phân tích kiểu phải xử lý lớp thường và hidden class. Cách nào đáng tin hơn: kiểm tra `!clazz.isHidden()` rồi gọi `describeConstable().get()`, hay dùng trực tiếp giá trị `Optional`?

**Đáp án:** Dùng trực tiếp `Optional`, vì `isHidden() == false` không bảo đảm mô tả danh định được, ví dụ mảng của hidden class.

## Ghi nhớ

**Hidden class có thể tồn tại và hoạt động tại runtime nhưng không thể được mô tả danh định.** Với `Class<?>` đại diện cho hidden class, `describeConstable()` trả `Optional.empty()`; điều tương tự xảy ra với mảng có phần tử hidden class. `getName()` và `descriptorString()` không tạo ra một binary name hay `ClassDesc` hợp lệ để tìm lại hidden class. Khi thiết kế API/framework, hãy xử lý trường hợp không có nominal descriptor như một khả năng bình thường và phân biệt rõ **mô tả ký hiệu**, **định danh runtime** và **khả năng thực thi qua Lookup/MethodHandle**.

### Tài liệu Java chính thức (đang áp dụng)

- [OpenJDK JEP 371 — Hidden Classes (Java 15)](https://openjdk.org/jeps/371)
- [Java SE 17 — Class: Hidden Classes, describeConstable, descriptorString, isHidden](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — MethodHandles.Lookup: defineHiddenClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 17 — ClassDesc: mô tả danh định và ofDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/ClassDesc.html)
- [Java SE 17 — Constable: Optional của nominal descriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/constant/Constable.html)
