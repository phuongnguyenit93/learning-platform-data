# Duyệt ngăn xếp hiện tại theo nhu cầu với StackWalker trong Java

## Mục tiêu

Java 9 bổ sung **StackWalker API** để chương trình duyệt các stack frame của luồng hiện tại theo nhu cầu. Thay vì tạo ngay một mảng stack trace đầy đủ, ứng dụng có thể xử lý từng frame, dừng sớm khi đã tìm thấy thông tin cần thiết hoặc chỉ lấy một số frame đầu tiên.

**StackWalker** phù hợp cho chẩn đoán, ghi log có chọn lọc, xác định caller và các công cụ cần quan sát ngăn xếp. API cho phép kiểm soát loại frame được hiển thị và, khi được cấu hình phù hợp, lấy tham chiếu lớp **Class<?>** của frame.

Bài này tập trung vào API hiện hành, cách dùng **walk()**, **forEach()**, **getCallerClass()**, **StackFrame**, các tùy chọn duyệt và những giới hạn cần hiểu khi làm việc với stack.

## 1. Stack frame và StackWalker

Một lần gọi phương thức tạo một frame trong call stack của thread. Frame chứa thông tin về phương thức đang thực thi, lớp khai báo, vị trí mã nguồn và một số thông tin liên quan.

Ví dụ, nếu **main()** gọi **service()** rồi **loadData()**, stack có thể được hình dung từ frame hiện tại lên các caller:

```text
loadData()
    ^
service()
    ^
main()
```

**StackWalker** cung cấp cách duyệt các frame đó từ frame hiện tại đi ngược về caller. Nó duyệt stack của thread đang gọi API; không phải công cụ để đọc stack của một thread bất kỳ khác.

Khác với việc tạo stack trace đầy đủ, StackWalker cho phép xử lý theo nhu cầu. Nếu chỉ cần caller gần nhất, không cần duyệt toàn bộ stack. Nếu chỉ cần vài frame để ghi log, có thể giới hạn số phần tử ngay trong pipeline.

Tạo một instance mặc định:

```java
StackWalker walker = StackWalker.getInstance();
```

Instance này dùng cấu hình mặc định và có thể được tái sử dụng cho nhiều lần duyệt. Mỗi lần gọi **walk()** hoặc **forEach()** sẽ quan sát stack của thread thực hiện lần gọi đó.

## 2. Hai cách duyệt: walk() và forEach()

StackWalker cung cấp hai phương thức chính để duyệt frame:

```java
<T> T walk(
        Function<? super Stream<StackFrame>, ? extends T> function);

void forEach(Consumer<? super StackFrame> action);
```

### walk()

**walk()** cung cấp một **Stream<StackWalker.StackFrame>** cho hàm xử lý. Hàm này có thể lọc, giới hạn, ánh xạ hoặc tìm kiếm frame, rồi trả về một kết quả bất kỳ.

Ví dụ lấy tên một số frame đầu tiên:

```java
List<String> frames = StackWalker.getInstance().walk(stream ->
        stream.limit(5)
                .map(frame -> frame.getClassName()
                        + "#" + frame.getMethodName())
                .toList());
```

**limit(5)** giúp dừng khi đã lấy đủ năm frame. Nếu stack ngắn hơn, kết quả chỉ chứa số frame thực tế có sẵn.

Một ưu điểm quan trọng của **walk()** là có thể dùng các thao tác short-circuit như **findFirst()**, **anyMatch()** hoặc **limit()**. Khi đã có kết quả, pipeline không cần tiếp tục duyệt các frame còn lại.

### forEach()

**forEach()** gọi một Consumer cho từng frame:

```java
StackWalker.getInstance().forEach(frame ->
        System.out.println(frame.getClassName()
                + "#" + frame.getMethodName()));
```

Cách này đơn giản khi cần xử lý tất cả frame. Tuy nhiên, nếu chỉ cần một frame hoặc một số lượng giới hạn, **walk()** thường phù hợp hơn vì có thể biểu đạt điều kiện dừng ngay trong pipeline.

### Không giữ Stream sau khi walk() kết thúc

Stream được truyền vào hàm của **walk()** chỉ hợp lệ trong phạm vi lần gọi đó. StackWalker đóng stream khi hàm xử lý trả về.

Không trả chính stream đó ra ngoài hoặc lưu nó để duyệt sau:

```java
// Không làm như sau:
Stream<StackWalker.StackFrame> saved =
        StackWalker.getInstance().walk(stream -> stream);
```

Thay vào đó, hãy chuyển thông tin cần dùng thành dữ liệu độc lập ngay bên trong hàm, chẳng hạn **String**, **List<String>** hoặc DTO chứa tên lớp, tên phương thức và số dòng.

## 3. Đọc thông tin từ StackFrame

Mỗi phần tử khi duyệt là một **StackWalker.StackFrame**. Các phương thức thường dùng:

| Phương thức | Thông tin |
|---|---|
| **getClassName()** | Tên lớp chứa phương thức |
| **getMethodName()** | Tên phương thức |
| **getFileName()** | Tên tệp nguồn nếu có |
| **getLineNumber()** | Số dòng nguồn; có thể không xác định |
| **isNativeMethod()** | Frame có đại diện cho phương thức native không |
| **toStackTraceElement()** | Chuyển thành **StackTraceElement** |
| **getDeclaringClass()** | Đối tượng **Class<?>** của lớp khai báo; cần **RETAIN_CLASS_REFERENCE** |

Ví dụ tạo thông tin log ngắn gọn:

```java
StackWalker.getInstance().walk(stream ->
        stream.limit(3).forEach(frame ->
                System.out.println(
                        frame.getClassName()
                                + "." + frame.getMethodName()
                                + "(" + frame.getFileName()
                                + ":" + frame.getLineNumber() + ")")));
```

Tên tệp hoặc số dòng có thể không có sẵn, ví dụ khi class không chứa thông tin debug tương ứng hoặc frame là native. Không nên giả định **getFileName()** luôn trả về chuỗi có giá trị hay **getLineNumber()** luôn là số dòng dương.

**getDeclaringClass()** khác với **getClassName()**: một phương thức trả về đối tượng Class, phương thức kia trả về tên lớp dạng chuỗi. Muốn dùng **getDeclaringClass()**, phải tạo StackWalker với tùy chọn **RETAIN_CLASS_REFERENCE**; nếu không, phương thức này ném **UnsupportedOperationException**.

## 4. Cấu hình StackWalker bằng Option

**StackWalker.Option** cho phép kiểm soát những loại frame được giữ lại và cách truy cập thông tin lớp.

Các tùy chọn cơ bản:

| Option | Ý nghĩa |
|---|---|
| **RETAIN_CLASS_REFERENCE** | Cho phép lấy tham chiếu Class<?> qua getDeclaringClass() và dùng getCallerClass() |
| **SHOW_REFLECT_FRAMES** | Hiển thị các frame liên quan đến reflection vốn được lọc theo mặc định |
| **SHOW_HIDDEN_FRAMES** | Hiển thị cả hidden frame; bao gồm các frame reflection |

Mặc định, StackWalker không hiển thị các frame reflection và hidden frame. Điều này giúp kết quả tập trung hơn vào lời gọi ứng dụng thông thường.

Tạo walker có quyền truy cập class reference:

```java
StackWalker walker = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE);
```

Muốn hiển thị frame reflection:

```java
StackWalker walker = StackWalker.getInstance(
        StackWalker.Option.SHOW_REFLECT_FRAMES);
```

Muốn hiển thị cả hidden frame:

```java
StackWalker walker = StackWalker.getInstance(
        StackWalker.Option.SHOW_HIDDEN_FRAMES);
```

Có thể kết hợp nhiều option bằng **Set**:

```java
StackWalker walker = StackWalker.getInstance(Set.of(
        StackWalker.Option.RETAIN_CLASS_REFERENCE,
        StackWalker.Option.SHOW_REFLECT_FRAMES));
```

Chỉ bật những option thật sự cần thiết. Khi bật reflection hoặc hidden frame, stack có thể chứa nhiều frame thuộc cơ chế thực thi của runtime hoặc thư viện, khiến việc đọc và phân tích phức tạp hơn.

## 5. Lấy caller bằng getCallerClass()

**getCallerClass()** trả về đối tượng **Class<?>** của caller của phương thức đã gọi nó. Đây là cách thuận tiện khi cần xác định lớp gọi một helper hoặc API.

Phương thức này yêu cầu walker được tạo với **RETAIN_CLASS_REFERENCE**. Nếu không có option đó, lời gọi ném **UnsupportedOperationException**.

Ví dụ một helper lấy tên lớp gọi nó:

```java
private static final StackWalker WALKER = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE);

static String callerName() {
    return WALKER.getCallerClass().getSimpleName();
}
```

Nếu **main()** gọi **callerName()**, kết quả là tên lớp chứa main(), tức lớp gọi helper.

Không nên thay **getCallerClass()** bằng cách lấy frame ở vị trí cố định như **skip(2)**. Stack có thể thay đổi khi thêm wrapper, framework, proxy hoặc các cơ chế gọi khác. **getCallerClass()** diễn đạt trực tiếp ý định lấy caller gần nhất theo hợp đồng API.

### Khi nào nên dùng caller information?

Một số trường hợp có thể cần caller:

- Tạo thông tin chẩn đoán cho API dùng chung.
- Xác định lớp gọi trong hệ thống logging hoặc tracing nội bộ.
- Phát hiện cách một helper được sử dụng trong một số công cụ phát triển.

Không nên dùng tên caller làm cơ chế phân quyền hoặc xác thực. Stack frame là thông tin thực thi để quan sát; quyền truy cập phải dựa trên cơ chế bảo mật và danh tính đáng tin cậy của ứng dụng.

## 6. Giới hạn độ sâu và hiệu năng

Có thể cung cấp độ sâu ước lượng khi tạo StackWalker:

```java
StackWalker walker = StackWalker.getInstance(
        Set.of(StackWalker.Option.RETAIN_CLASS_REFERENCE),
        32);
```

Tham số này là **ước lượng độ sâu** để runtime có thể chuẩn bị tài nguyên phù hợp. Nó không phải giới hạn số frame tối đa và không thay thế **limit()** trong pipeline.

Nếu muốn chỉ xử lý tối đa 10 frame, vẫn phải viết:

```java
List<String> frames = walker.walk(stream ->
        stream.limit(10)
                .map(StackWalker.StackFrame::getMethodName)
                .toList());
```

Để giữ chi phí thấp:

- Chỉ tạo thông tin cần dùng thay vì chuyển toàn bộ stack thành chuỗi.
- Dùng **limit()** hoặc thao tác tìm kiếm để dừng sớm.
- Tránh gọi StackWalker liên tục trong vòng lặp nóng nếu không cần thiết.
- Chỉ bật **SHOW_REFLECT_FRAMES** hoặc **SHOW_HIDDEN_FRAMES** khi có mục đích cụ thể.
- Dùng walker đã cấu hình phù hợp và tái sử dụng khi cần.

Không có một chi phí cố định cho mọi lần duyệt: độ sâu stack, số frame cần xử lý, JIT và cấu hình runtime đều có thể ảnh hưởng. Nếu hiệu năng là yêu cầu quan trọng, hãy đo trong workload thực tế.

## 7. StackWalker và các cách đọc stack khác

Java có nhiều cách quan sát stack, nhưng mục đích sử dụng khác nhau:

| Cách tiếp cận | Đặc điểm | Khi phù hợp |
|---|---|---|
| **StackWalker.walk()** | Duyệt lazy, hỗ trợ lọc và dừng sớm | Chỉ cần một phần stack hoặc cần truy cập class reference |
| **StackWalker.forEach()** | Duyệt các frame bằng Consumer | Cần xử lý từng frame |
| **Thread.currentThread().getStackTrace()** | Trả mảng StackTraceElement | Cần một snapshot đơn giản của stack hiện tại |
| **new Throwable().getStackTrace()** | Lấy stack trace gắn với Throwable | Chẩn đoán lỗi hoặc ghi lại vị trí tạo Throwable |

StackWalker phù hợp khi muốn kiểm soát quá trình duyệt. Nếu chỉ cần stack trace gắn với exception, không nhất thiết phải thay thế bằng StackWalker.

Không nên phân tích chuỗi stack trace để điều khiển logic nghiệp vụ. Tên phương thức, thứ tự frame và cấu trúc gọi có thể thay đổi khi refactor, tối ưu hoặc dùng framework.

## 8. Ví dụ Java hoàn chỉnh

Ví dụ sau minh họa hai việc: lấy caller class bằng **getCallerClass()** và lấy tối đa năm frame bằng **walk()**. Mã chuyển frame thành chuỗi ngay trong callback để không giữ stream sau khi **walk()** kết thúc.

Tạo tệp **StackWalkerDemo.java**:

```java
import java.util.List;
import java.util.Set;

public class StackWalkerDemo {
    private static final StackWalker WALKER = StackWalker.getInstance(
            Set.of(StackWalker.Option.RETAIN_CLASS_REFERENCE));

    private static final class CallerLookup {
        static String callerName() {
            return WALKER.getCallerClass().getSimpleName();
        }
    }

    private static List<String> captureFrames() {
        return WALKER.walk(stream -> stream
                .limit(5)
                .map(frame -> frame.getClassName()
                        + "#" + frame.getMethodName())
                .toList());
    }

    public static void main(String[] args) {
        System.out.println("caller: " + CallerLookup.callerName());
        System.out.println("frames:");
        captureFrames().forEach(frame ->
                System.out.println("  " + frame));
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac --release 17 StackWalkerDemo.java
java StackWalkerDemo
```

Stdout chính xác:

```text
caller: StackWalkerDemo
frames:
  StackWalkerDemo#captureFrames
  StackWalkerDemo#main
```

Kết quả cho thấy helper **CallerLookup.callerName()** nhận diện lớp gọi là StackWalkerDemo. Phương thức **captureFrames()** chỉ giữ hai frame có sẵn trong stack của lần chạy này; **limit(5)** không tạo thêm frame nếu stack ngắn hơn giới hạn.

## 9. Lỗi thường gặp và cách tránh

1. **Duyệt toàn bộ stack khi chỉ cần một frame**: dùng **walk()** kết hợp **findFirst()**, **limit()** hoặc thao tác short-circuit.
2. **Giữ stream sau khi walk() kết thúc**: stream bị đóng khi hàm truyền vào **walk()** trả về. Hãy trích xuất dữ liệu cần dùng ngay bên trong callback.
3. **Gọi getDeclaringClass() với walker mặc định**: cần cấu hình **RETAIN_CLASS_REFERENCE**; nếu thiếu, phương thức ném **UnsupportedOperationException**.
4. **Gọi getCallerClass() mà không bật RETAIN_CLASS_REFERENCE**: cấu hình walker với option này trước khi dùng.
5. **Nhầm estimateDepth với giới hạn frame**: đây chỉ là độ sâu ước lượng. Dùng **limit()** để giới hạn kết quả.
6. **Giả định mọi frame có file và số dòng**: thông tin nguồn có thể không có sẵn. Xử lý trường hợp **getFileName()** trả null hoặc số dòng không xác định.
7. **Phân tích stack theo vị trí cố định**: thêm wrapper hoặc framework có thể làm thay đổi thứ tự frame. Dùng **getCallerClass()** khi mục tiêu là lấy caller.
8. **Bật tất cả frame mà không cần thiết**: reflection và hidden frame làm kết quả phức tạp hơn. Chỉ bật option cần cho mục tiêu chẩn đoán.
9. **Dùng stack để phân quyền**: caller name không phải danh tính bảo mật đáng tin cậy. Dùng cơ chế xác thực và phân quyền chuyên dụng.
10. **Giả định StackWalker đọc stack của thread khác**: mỗi lần duyệt quan sát stack của thread thực hiện lời gọi.

## Kết luận

**StackWalker** trong Java 9 cho phép duyệt stack frame của thread hiện tại theo nhu cầu. **walk()** cung cấp Stream để lọc, giới hạn và tìm kiếm; **forEach()** xử lý từng frame; **getCallerClass()** lấy caller class khi walker có **RETAIN_CLASS_REFERENCE**.

Hãy chỉ duyệt số frame cần thiết, xử lý stream bên trong callback của **walk()**, chọn option phù hợp và coi thông tin stack là dữ liệu chẩn đoán. Cách dùng này giúp tránh tạo và xử lý stack trace đầy đủ khi ứng dụng chỉ cần một phần thông tin.
