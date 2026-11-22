# Flag không thể đổi trong jinfo

**`jinfo`** là công cụ chẩn đoán của JDK dùng để đọc cấu hình JVM đang chạy, bao gồm VM flags và Java system properties. Công cụ cũng có thể thay đổi một số VM flag trong lúc JVM hoạt động. Tuy nhiên, **không phải flag nào cũng có thể thay đổi sau khi JVM khởi động**.

Những flag không hỗ trợ thay đổi động thường phải được đặt trước khi chạy ứng dụng. Nếu cố thay đổi, `jinfo` có thể trả lỗi như:

```text
flag 'MaxHeapSize' cannot be changed
```

Hiểu sự khác nhau giữa flag có thể quản lý lúc chạy (*manageable*) và flag chỉ có hiệu lực khi khởi động giúp tránh nhầm lẫn khi cấu hình heap, garbage collector hoặc các thành phần runtime khác.

## 1. VM flag là gì?

VM flag là tùy chọn điều khiển hành vi của Java Virtual Machine (JVM). Phần lớn flag được truyền khi khởi chạy ứng dụng bằng `java`, thường có tiền tố `-X` hoặc `-XX:`.

Ví dụ:

```bash
java -Xms256m -Xmx2g -XX:+UseG1GC -Dapp.profile=production -jar app.jar
```

Ý nghĩa:

- `-Xms256m`: kích thước heap ban đầu.
- `-Xmx2g`: giới hạn heap tối đa.
- `-XX:+UseG1GC`: yêu cầu dùng G1 garbage collector.
- `-Dapp.profile=production`: đặt Java system property cho ứng dụng.

Các flag có thể điều khiển:

- Heap và garbage collection.
- JIT compiler và code cache.
- Thread, stack và runtime.
- Native memory và class metadata.
- Diagnostic logging và heap dump.
- Các tính năng JVM khác.

Không phải mọi flag đều có thể đổi trong lúc ứng dụng đang chạy. Một số giá trị được JVM dùng để tạo cấu trúc bộ nhớ hoặc khởi tạo thành phần runtime ngay từ đầu.

## 2. jinfo hỗ trợ những thao tác nào?

Cú pháp tổng quát:

```text
jinfo <option> <pid>
```

Trong đó `pid` là process ID của JVM đang chạy.

Xem trợ giúp:

```bash
jinfo -h
```

Các tùy chọn chính:

| Lệnh | Công dụng |
| --- | --- |
| `jinfo <pid>` | In VM flags và Java system properties |
| `jinfo -flags <pid>` | In các VM flags |
| `jinfo -flag <name> <pid>` | Đọc giá trị của một VM flag |
| `jinfo -flag +<name> <pid>` | Bật một Boolean VM flag |
| `jinfo -flag -<name> <pid>` | Tắt một Boolean VM flag |
| `jinfo -flag <name>=<value> <pid>` | Đặt giá trị cho một VM flag nếu flag hỗ trợ thay đổi |
| `jinfo -sysprops <pid>` | In Java system properties |

Ví dụ đọc giới hạn heap:

```bash
jinfo -flag MaxHeapSize 18420
```

Ví dụ đọc flag Boolean:

```bash
jinfo -flag UseG1GC 18420
```

Ví dụ đọc system properties:

```bash
jinfo -sysprops 18420
```

Các lệnh trên chỉ truy vấn trạng thái; chúng không thay đổi cấu hình của JVM.

## 3. Vì sao có flag không thể đổi?

Một số VM flag chỉ được đọc khi JVM khởi tạo. JVM cần những giá trị này để tạo heap, chọn garbage collector, thiết lập vùng nhớ hoặc cấu hình thành phần runtime.

Sau khi tiến trình đã chạy, thay đổi một giá trị có thể yêu cầu tái cấu trúc tài nguyên mà JVM không hỗ trợ thay thế an toàn.

Ví dụ điển hình là `MaxHeapSize`, thường được thiết lập bằng `-Xmx` lúc khởi động. JVM dùng giới hạn này để thiết lập vùng heap. Bạn có thể đọc giá trị hiện tại bằng `jinfo`, nhưng không thể tăng hoặc giảm nó tùy ý trong tiến trình đang chạy.

Các flag khác có thể được thay đổi động nếu JVM đánh dấu chúng là manageable. Khả năng thay đổi phụ thuộc từng flag, phiên bản JVM và implementation/provider.

**Không suy luận chỉ từ tên flag hoặc tiền tố `-XX:`.** Cần kiểm tra metadata của flag trên chính JVM đang chạy.

## 4. Phân biệt manageable và non-manageable flags

HotSpot phân loại một số flag là **manageable**. Những flag này được thiết kế để có thể thay đổi qua giao diện quản lý khi JVM hoạt động.

Flag không có thuộc tính manageable thường không được phép thay đổi động qua `jinfo` hoặc `jcmd VM.set_flag`.

| Loại | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Manageable | JVM cho phép thay đổi giá trị lúc chạy | Có thể dùng `jinfo -flag name=value` hoặc `jcmd VM.set_flag` nếu lệnh và giá trị được hỗ trợ |
| Non-manageable | Không hỗ trợ thay đổi qua giao diện quản lý lúc chạy | Đặt giá trị khi khởi động JVM rồi restart ứng dụng |
| Unknown/unsupported | JVM hiện tại không nhận diện flag hoặc không hỗ trợ thao tác | Kiểm tra tên flag, JDK version và provider |

Có thể dùng `jcmd <pid> VM.flags -all` để xem metadata của các flag. Ví dụ output:

```text
size_t MaxHeapSize       = 268435456  {product} {command line}
uintx MinHeapFreeRatio   = 20         {manageable} {default}
```

Đây là output minh họa. Các thuộc tính trong dấu ngoặc nhọn có ý nghĩa khác nhau:

- `{manageable}`: flag được JVM đánh dấu có thể quản lý/thay đổi động.
- `{product}`: phân loại flag trong HotSpot.
- `{command line}`: nguồn giá trị được thiết lập từ command line.
- `{default}` hoặc `{ergonomic}`: nguồn giá trị mặc định hoặc do JVM tự lựa chọn.

Không nhầm `{product}` với `{manageable}`. Một flag là product flag vẫn có thể không cho phép thay đổi động.

## 5. Đọc giá trị flag không thể đổi

Dùng `jinfo -flag` để đọc giá trị hiện tại:

```bash
jinfo -flag MaxHeapSize 18420
```

Output minh họa:

```text
-XX:MaxHeapSize=268435456
```

Giá trị `268435456` byte tương đương 256 MiB.

Có thể xem toàn bộ flag:

```bash
jinfo -flags 18420
```

Hoặc dùng lệnh mới hơn:

```bash
jcmd 18420 VM.flags -all
```

Trong output `VM.flags -all`, tìm tên flag và kiểm tra xem có thuộc tính `{manageable}` hay không.

Việc đọc được giá trị không có nghĩa là có thể thay đổi nó. `jinfo -flag MaxHeapSize <pid>` thành công chỉ xác nhận công cụ có thể truy vấn flag.

## 6. Thử thay đổi một flag non-manageable

Ví dụ JVM đang chạy với:

```bash
java -Xms64m -Xmx256m -cp out FlagTarget
```

Đọc giá trị:

```bash
jinfo -flag MaxHeapSize 18420
```

Output:

```text
-XX:MaxHeapSize=268435456
```

Thử đặt giới hạn heap thành 512 MiB:

```bash
jinfo -flag MaxHeapSize=536870912 18420
```

JVM trả lỗi tương tự:

```text
Exception in thread "main" com.sun.tools.attach.AttachOperationFailedException:
flag 'MaxHeapSize' cannot be changed
```

Lỗi này cho biết flag không hỗ trợ thay đổi động. Tiến trình hiện tại vẫn giữ giới hạn heap ban đầu.

Không có cú pháp `jinfo` nào có thể ép JVM thay đổi một flag bị đánh dấu không thể ghi. Muốn dùng giới hạn mới, cần khởi động lại ứng dụng với tùy chọn phù hợp.

## 7. Thay đổi flag manageable trong lúc JVM chạy

Ví dụ `MinHeapFreeRatio` là flag được HotSpot đánh dấu manageable trên JVM kiểm thử.

Đọc giá trị hiện tại:

```bash
jinfo -flag MinHeapFreeRatio 18420
```

Output:

```text
-XX:MinHeapFreeRatio=20
```

Thay đổi từ 20 thành 25:

```bash
jinfo -flag MinHeapFreeRatio=25 18420
```

Đọc lại:

```bash
jinfo -flag MinHeapFreeRatio 18420
```

Output:

```text
-XX:MinHeapFreeRatio=25
```

Giá trị mới được áp dụng cho JVM đang chạy. Ví dụ này cho thấy `jinfo` có thể thay đổi một số flag; khả năng đó phụ thuộc thuộc tính manageable của từng flag.

Để kiểm tra lại metadata:

```bash
jcmd 18420 VM.flags -all
```

Dòng tương ứng có thể hiển thị:

```text
uintx MinHeapFreeRatio = 25 {manageable} {management}
```

Đặt giá trị về 20 nếu đây chỉ là thao tác thử nghiệm:

```bash
jinfo -flag MinHeapFreeRatio=20 18420
```

Không thay đổi flag production chỉ để thử nghiệm. Trước khi đổi một flag manageable, hãy đọc tài liệu của flag và đánh giá tác động đến workload.

## 8. Dùng jcmd thay cho jinfo

`jinfo` là công cụ experimental và unsupported theo tài liệu JDK. Oracle khuyến nghị sử dụng `jcmd` cho chẩn đoán JVM hiện đại.

Đọc toàn bộ VM flags và metadata:

```bash
jcmd 18420 VM.flags -all
```

Đọc flag cụ thể:

```bash
jcmd 18420 VM.flags
```

Thay đổi một flag manageable:

```bash
jcmd 18420 VM.set_flag MinHeapFreeRatio 25
```

Sau đó xác minh:

```bash
jcmd 18420 VM.flags -all
```

Nếu thử thay đổi flag không thể ghi:

```bash
jcmd 18420 VM.set_flag MaxHeapSize 536870912
```

JVM có thể trả thông báo:

```text
only 'writeable' flags can be set
```

Thông báo này cho biết flag không được phép thay đổi qua cơ chế runtime management.

`jcmd` là lựa chọn phù hợp hơn cho quy trình chẩn đoán hiện đại. Tuy nhiên, nó cũng không thể thay đổi flag non-manageable; giới hạn nằm ở khả năng của JVM chứ không phải ở cú pháp của công cụ.

## 9. Khi flag không thể đổi, cần làm gì?

Nếu flag là non-manageable, cách xử lý là thay đổi cấu hình khởi động và restart JVM.

Ví dụ ứng dụng đang chạy với:

```bash
java -Xms64m -Xmx256m -jar app.jar
```

Muốn tăng heap tối đa lên 512 MiB, cập nhật lệnh khởi chạy:

```bash
java -Xms64m -Xmx512m -jar app.jar
```

Các bước vận hành:

1. Đọc giá trị hiện tại bằng `jinfo -flag` hoặc `jcmd VM.flags -all`.
2. Xác định flag có thuộc tính manageable không.
3. Nếu non-manageable, cập nhật cấu hình khởi động của service/container/script.
4. Đánh giá bộ nhớ máy và giới hạn container trước khi tăng heap.
5. Lập kế hoạch restart theo quy trình triển khai.
6. Khởi động lại JVM với giá trị mới.
7. Xác minh bằng `jcmd <pid> VM.flags -all` hoặc `jinfo -flag`.

Với ứng dụng chạy qua systemd, Docker, Kubernetes hoặc service manager, hãy thay đổi cấu hình ở nơi quản lý process. Chỉnh sửa một terminal command không làm thay đổi cấu hình mà orchestrator sẽ dùng cho lần restart kế tiếp.

## 10. Ví dụ thực hành Java 17: kiểm tra flag trên JVM đang chạy

Tạo tệp **`FlagTarget.java`**:

```java
public final class FlagTarget {
    private FlagTarget() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY=" + ProcessHandle.current().pid());
        Thread.sleep(120_000);
    }
}
```

Chương trình in PID rồi giữ JVM hoạt động trong 120 giây để có thể gửi diagnostic command từ terminal khác.

Biên dịch:

```bash
javac --release 17 FlagTarget.java
```

Chạy với heap 256 MiB và một flag manageable:

```bash
java -Xms64m -Xmx256m -XX:MinHeapFreeRatio=20 FlagTarget
```

Output:

```text
READY=18420
```

PID là giá trị động; dùng PID thực tế được chương trình in ra.

Mở terminal thứ hai và kiểm tra:

```bash
jinfo -flag MaxHeapSize 18420
jinfo -flag MinHeapFreeRatio 18420
jcmd 18420 VM.flags -all
```

Thử thay đổi flag manageable:

```bash
jinfo -flag MinHeapFreeRatio=25 18420
jinfo -flag MinHeapFreeRatio 18420
```

Kết quả mong đợi:

```text
-XX:MinHeapFreeRatio=25
```

Thử thay đổi MaxHeapSize:

```bash
jinfo -flag MaxHeapSize=536870912 18420
```

Kết quả mong đợi là lỗi `flag 'MaxHeapSize' cannot be changed`.

Xem lại giá trị heap:

```bash
jinfo -flag MaxHeapSize 18420
```

Giá trị vẫn là:

```text
-XX:MaxHeapSize=268435456
```

Sau khi thử nghiệm, dừng tiến trình bằng Ctrl+C ở terminal đang chạy `FlagTarget`. Ví dụ này đã được biên dịch bằng `javac --release 17` và kiểm tra trên HotSpot JDK 24.0.2; chi tiết flag có thể thay đổi theo phiên bản JVM.

## 11. Phân biệt VM flags và Java system properties

Một nhầm lẫn phổ biến là coi Java system property và VM flag là cùng một loại cấu hình.

| Loại | Ví dụ | Cách đọc |
| --- | --- | --- |
| VM flag | `MaxHeapSize`, `MinHeapFreeRatio`, `UseG1GC` | `jinfo -flag`, `jinfo -flags`, `jcmd VM.flags` |
| Java system property | `app.profile`, `java.io.tmpdir`, `user.timezone` | `jinfo -sysprops`, `jcmd VM.system_properties`, `System.getProperty()` |

Đặt system property khi khởi động:

```bash
java -Dapp.profile=production -jar app.jar
```

Đọc property trong Java:

```java
String profile = System.getProperty("app.profile");
```

Mã ứng dụng có thể gọi `System.setProperty("app.profile", "staging")` để thay đổi property trong tiến trình hiện tại. Tuy nhiên, thư viện đã đọc và lưu giá trị trước đó có thể không tự cập nhật. Thay đổi system property cũng không làm thay đổi VM flag như `MaxHeapSize`.

`jinfo -sysprops <pid>` chỉ in các system properties; nó không phải lệnh để thay đổi property.

## 12. Boolean flag và flag có giá trị số

`jinfo` có hai dạng thay đổi flag:

**Boolean flag:**

```bash
jinfo -flag +HeapDumpOnOutOfMemoryError 18420
jinfo -flag -HeapDumpOnOutOfMemoryError 18420
```

Dạng `+` bật flag; dạng `-` tắt flag. Chỉ dùng nếu flag cụ thể hỗ trợ thay đổi động và JVM cho phép thao tác.

**Flag có giá trị:**

```bash
jinfo -flag MinHeapFreeRatio=25 18420
```

Giá trị có thể là số hoặc chuỗi theo kiểu flag. JVM kiểm tra kiểu và giới hạn của giá trị. Flag manageable vẫn có thể từ chối giá trị ngoài miền hợp lệ.

Trước khi đổi:

1. Kiểm tra tên flag và giá trị hiện tại.
2. Xác nhận flag được đánh dấu manageable.
3. Đọc mô tả và miền giá trị hợp lệ.
4. Ghi lại giá trị ban đầu để có thể khôi phục.
5. Thay đổi trong phạm vi kiểm soát.
6. Đọc lại giá trị và quan sát tác động.

Không dùng `+` hoặc `-` với flag không phải Boolean.

## 13. Vì sao không nên cố thay đổi flag non-manageable?

Việc một flag không thể đổi là giới hạn thiết kế của JVM. Cố tìm cách vượt qua giới hạn này có thể khiến cấu hình runtime không nhất quán hoặc làm ứng dụng mất ổn định.

Ví dụ, heap maximum ảnh hưởng đến cách JVM quản lý heap. Nếu thay đổi tùy ý sau khi runtime đã khởi tạo, JVM có thể phải thay đổi cấu trúc bộ nhớ và các giả định mà collector đang sử dụng.

Khi một flag không thể đổi:

- Không lặp lại lệnh với nhiều giá trị ngẫu nhiên.
- Không thay đổi các flag liên quan chỉ để né lỗi.
- Không tắt attach hoặc security mechanism để tìm cách ép ghi.
- Không sửa file cấu hình của process đang chạy với kỳ vọng JVM tự nạp lại.
- Thay đổi cấu hình khởi động và restart theo quy trình vận hành.

Lỗi `cannot be changed` là tín hiệu để chuyển sang quy trình thay đổi startup configuration.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `flag 'MaxHeapSize' cannot be changed` | Flag không hỗ trợ thay đổi động | Đặt `-Xmx` mới và restart JVM |
| `only 'writeable' flags can be set` | Flag không được JVM đánh dấu có thể ghi | Kiểm tra `VM.flags -all`, dùng flag manageable hoặc restart |
| Không tìm thấy flag | Sai tên hoặc flag không tồn tại trong JVM hiện tại | Kiểm tra `jcmd <pid> VM.flags -all` |
| Giá trị bị từ chối | Giá trị sai kiểu hoặc ngoài miền hợp lệ | Đọc trợ giúp/tài liệu flag và dùng giá trị hợp lệ |
| Không attach được process | Sai PID, khác user hoặc attach bị vô hiệu hóa | Xác nhận PID, quyền và cấu hình JVM |
| Thay đổi thành công nhưng hành vi không đổi | Flag chỉ tác động đến hoạt động tương lai hoặc ứng dụng không chịu ảnh hưởng trong workload hiện tại | Xác minh lại giá trị và quan sát workload |
| Không thấy flag trong output mặc định | Flag không được in ở chế độ rút gọn hoặc cần xem toàn bộ metadata | Dùng `jcmd <pid> VM.flags -all` |
| Không đọc được system property | Nhầm system property với VM flag hoặc process không cho attach | Dùng `jinfo -sysprops` hoặc `jcmd VM.system_properties` |

## 15. Lưu ý về phiên bản và công cụ

`jinfo` được tài liệu JDK đánh dấu là **experimental và unsupported**. Công cụ có thể thay đổi hoặc không còn được cung cấp trong các bản JDK tương lai. Oracle khuyến nghị dùng `jcmd` cho chẩn đoán JVM hiện đại.

Ngoài ra:

- Dùng JDK tool phù hợp với phiên bản JVM đích.
- Attach cần quyền truy cập process theo chính sách hệ điều hành.
- JVM có thể được khởi chạy với `-XX:+DisableAttachMechanism`, khi đó công cụ attach không hoạt động.
- Trong container, cần chú ý PID namespace và user chạy JVM.
- Một số flag hoặc tùy chọn phụ thuộc HotSpot và có thể không tồn tại ở JVM khác.
- Không parse output công cụ thành định dạng ổn định cho automation nếu không kiểm soát phiên bản.

Với quy trình vận hành mới, ưu tiên `jcmd` và management interface được hỗ trợ. Dù dùng công cụ nào, flag non-manageable vẫn cần được đặt lúc khởi động.

## 16. Quy trình xử lý flag không thể đổi

Khi nhận lỗi không thể thay đổi flag:

1. Ghi lại PID, JDK version và tên flag.
2. Đọc giá trị hiện tại bằng `jinfo -flag` hoặc `jcmd VM.flags -all`.
3. Kiểm tra metadata `{manageable}`.
4. Nếu flag manageable, kiểm tra kiểu, giá trị và cú pháp cập nhật.
5. Nếu flag không manageable, xác định tùy chọn khởi động tương ứng.
6. Cập nhật service/container/deployment configuration.
7. Đánh giá tài nguyên và lên lịch restart.
8. Khởi động lại JVM với giá trị mới.
9. Xác minh giá trị sau restart.
10. Theo dõi heap, GC, latency và các chỉ số liên quan sau thay đổi.

Ví dụ cần tăng heap:

```bash
# Cấu hình cũ
java -Xms64m -Xmx256m -jar app.jar

# Cấu hình mới sau khi cập nhật startup configuration
java -Xms64m -Xmx512m -jar app.jar
```

Sau restart, kiểm tra:

```bash
jcmd <new-pid> VM.flags -all
```

Xác nhận `MaxHeapSize` đã phản ánh cấu hình mới. PID có thể thay đổi sau khi restart.

## 17. Ghi nhớ

- `jinfo` đọc VM flags và system properties của JVM đang chạy.
- `jinfo -flag <name> <pid>` đọc giá trị một flag.
- `jinfo -flag <name>=<value> <pid>` chỉ thay đổi được flag hỗ trợ runtime management.
- Flag có thuộc tính `{manageable}` có thể thay đổi động nếu giá trị hợp lệ.
- Flag non-manageable như `MaxHeapSize` không thể thay đổi trong tiến trình hiện tại.
- Lỗi `flag 'MaxHeapSize' cannot be changed` nghĩa là cần thay đổi startup option và restart.
- Dùng `jcmd <pid> VM.flags -all` để xem giá trị và metadata flag.
- Dùng `jcmd <pid> VM.set_flag <name> <value>` cho flag có thể ghi.
- VM flags khác Java system properties; `jinfo -sysprops` chỉ đọc system properties.
- `jinfo` là công cụ experimental/unsupported; ưu tiên `jcmd` trong quy trình mới.

Hiểu flag nào có thể đổi và flag nào chỉ được thiết lập lúc khởi động giúp bạn điều chỉnh JVM đúng cách, tránh gián đoạn ứng dụng do thử thay đổi những cấu hình runtime không hỗ trợ.
