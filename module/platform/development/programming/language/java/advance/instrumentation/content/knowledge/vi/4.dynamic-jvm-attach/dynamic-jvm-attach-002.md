# Khám phá tiến trình JVM bằng VirtualMachine.list() và VirtualMachineDescriptor

Một công cụ profiler, debugger hoặc Java agent launcher thường cần **tìm đúng tiến trình Java đang chạy** trước khi quyết định có kết nối vào JVM đó hay không. Attach API cung cấp `VirtualMachine.list()` để khám phá JVM và `VirtualMachineDescriptor` để đọc thông tin nhận diện do *attach provider* cung cấp.

Bài này tập trung vào **bước khám phá và lựa chọn ứng viên**: cách lấy danh sách, hiểu đúng ID/tên hiển thị/provider, lọc tiến trình và xử lý trường hợp không tìm thấy. Việc liệt kê **không tự attach**, không nạp agent và không bảo đảm rằng một tiến trình được liệt kê có thể attach thành công.

## 1. Vị trí của bước khám phá trong quy trình instrumentation

Luồng làm việc điển hình:

~~~text
Ứng dụng công cụ chạy trên JDK
              |
              v
VirtualMachine.list()
              |
              v
List<VirtualMachineDescriptor>
              |
              v
Xem id / displayName / provider
              |
              v
Lọc và xác minh đúng JVM mục tiêu
              |
              v
[Quyết định attach ở bước riêng, nếu được phép]
~~~

Trong luồng này:

- **Discover**: tìm các JVM mà các attach provider hiện tại *biết tới*.
- **Identify**: chọn đúng JVM bằng thông tin nhận diện; tránh dựa duy nhất vào tên hiển thị.
- **Attach**: thao tác riêng, thực hiện về sau bằng `VirtualMachine.attach(...)`, có thể thất bại ngay cả khi giai đoạn Discover thành công.

Các lớp chính nằm trong **module JDK `jdk.attach`**:

| API | Vai trò |
| --- | --- |
| `com.sun.tools.attach.VirtualMachine` | Lớp mô tả kết nối tới JVM sau khi attach; cũng chứa phương thức tĩnh `list()` |
| `com.sun.tools.attach.VirtualMachineDescriptor` | Thông tin nhận diện một JVM do provider phát hiện; chưa phải kết nối |
| `com.sun.tools.attach.spi.AttachProvider` | Cơ chế phụ thuộc nền tảng/JVM vendor để liệt kê và có thể attach |
| `java.lang.ProcessHandle` | API của Java để xem thông tin tiến trình hệ điều hành; **khác** Attach API |

Dùng **JDK 17 trở lên có module `jdk.attach`** để biên dịch và chạy ví dụ. Một runtime tùy biến tạo bằng `jlink` có thể không chứa module này. Nếu ứng dụng có `module-info.java`, khai báo `requires jdk.attach;`; ví dụ bên dưới là chương trình trên classpath nên sử dụng tùy chọn `--add-modules jdk.attach` rõ ràng.

## 2. Chính xác thì VirtualMachine.list() làm gì?

Chữ ký phương thức:

~~~java
public static List<VirtualMachineDescriptor> list()
~~~

Gọi `VirtualMachine.list()` sẽ tổng hợp các danh sách `VirtualMachineDescriptor` từ `listVirtualMachines()` của **mọi attach provider đã cài đặt**. Nếu không provider nào biết JVM nào, kết quả là **danh sách rỗng**. Phương thức này không yêu cầu truyền PID, mẫu tên hoặc một `VirtualMachineDescriptor` có sẵn.

Điểm cần nắm:

1. **Không phải liệt kê toàn bộ tiến trình của OS.** Danh sách là những JVM mà các attach provider có thể phát hiện; tiến trình trình duyệt, database hoặc ứng dụng native không phải JVM sẽ không vì thế xuất hiện.
2. **Không phải danh sách bảo đảm đầy đủ mọi JVM trên máy.** Khả năng phát hiện phụ thuộc triển khai JDK/JVM, provider, hệ điều hành, quyền truy cập, vùng chứa và cơ chế nhận diện tiến trình.
3. **Không phải phép kiểm tra attach thành công.** Theo contract của `AttachProvider.listVirtualMachines()`, một descriptor được liệt kê chỉ là JVM mà provider **có khả năng** attach; không có bảo đảm thao tác attach thực tế sẽ thành công.
4. **Kết quả phản ánh thời điểm quét.** JVM có thể khởi động hoặc dừng ngay sau lời gọi. Không được coi các descriptor thu được là những kết nối đã giữ sống tiến trình.
5. **Không có thứ tự mặc định được bảo đảm.** Nếu hiển thị cho người dùng hoặc so sánh hai lần quét, hãy tự sắp xếp theo tiêu chí ổn định.
6. **Không có đối số tìm kiếm trong `list()`.** Muốn lọc theo tên/id thì lọc `List<VirtualMachineDescriptor>` ở phía ứng dụng.

Để biết đang có những provider nào:

~~~java
List<AttachProvider> providers = AttachProvider.providers();
~~~

Khi số provider là 0, `list()` không có nguồn liệt kê, nên một kết quả rỗng không thể được hiểu là "máy này không chạy JVM nào". Khi provider có mặt nhưng danh sách rỗng, vẫn cần xem khả năng nhìn thấy tiến trình và quyền của môi trường chạy.

## 3. VirtualMachineDescriptor chứa thông tin gì?

Một `VirtualMachineDescriptor` là đối tượng mô tả **JVM được tìm thấy**, không phải đối tượng `VirtualMachine` đã attach. Ba phương thức thường dùng:

| Phương thức | Kiểu trả về | Cách sử dụng và giới hạn |
| --- | --- | --- |
| `id()` | `String` | Định danh do provider cung cấp; **thường là PID dạng chuỗi**, nhưng có thể khác tùy triển khai |
| `displayName()` | `String` | Chuỗi dễ đọc để hiển thị cho người dùng; **không bảo đảm duy nhất**, không nhất thiết là tên class |
| `provider()` | `AttachProvider` | Provider đi kèm descriptor; dùng để nhận diện cơ chế có thể attach tới JVM đó |

Đối với provider, `name()` cho tên provider và `type()` cho loại cơ chế (ví dụ trên một nền tảng nhất định có thể là `sun/windows` hoặc `sun/socket`). Những chuỗi này phụ thuộc JDK và môi trường; **không hard-code** một tên provider làm tiêu chí nhận diện portable.

### ID không phải lúc nào cũng là PID

Trên nhiều hệ thống, `descriptor.id()` là chuỗi chữ số tương ứng PID của tiến trình JVM, chẳng hạn `"7421"`. Tuy nhiên Attach API định nghĩa nó là **identifier phụ thuộc triển khai**. Vì vậy:

- Giữ ID dưới dạng `String` khi hiển thị, lưu lại hoặc truyền cho API.
- Không mặc định gọi `Long.parseLong(descriptor.id())`; có provider không dùng PID số.
- Ngay cả khi ID là PID, PID có thể được **tái sử dụng** khi tiến trình cũ kết thúc, và PID nhìn từ container có thể khác PID phía host.
- Nếu nhiều provider cùng trả về chuỗi ID giống nhau, cần xét **cả provider** để phân biệt; ID đơn lẻ không nhất thiết là khóa toàn cục.

### displayName không phải khóa định danh

Một `displayName()` có thể trông như tên main class, tên JAR hoặc câu lệnh khởi động do runtime cung cấp, ví dụ `com.example.OrderService` hoặc `order-service.jar`. Đó chỉ là thông tin hiển thị, không có hợp đồng rằng nó phải chứa một tên class/JAR nhất định. Nếu provider không có display name riêng thì giá trị có thể **bằng `id()`**.

Hai JVM chạy cùng ứng dụng có thể có **displayName giống nhau**. Ngược lại, một JVM cụ thể có thể hiển thị khác nhau tùy cách khởi động và JVM implementation. Do đó lọc theo tên hữu ích để **thu hẹp danh sách**, nhưng quyết định attach cần kiểm tra ID, provider và ngữ cảnh hệ thống.

### provider() không phải hành động attach

`descriptor.provider()` trả về provider liên kết với descriptor. Lời gọi này chỉ đọc metadata; nó không mở kết nối. Tương tự, `toString()` hoặc `displayName()` không cho biết JVM đang chạy version nào, thuộc user nào hay đã cho phép attach hay chưa. Những thông tin đó không nằm trong contract của `VirtualMachineDescriptor`.

## 4. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp **`JvmDiscovery.java`**:

~~~java
import com.sun.tools.attach.VirtualMachine;
import com.sun.tools.attach.VirtualMachineDescriptor;
import com.sun.tools.attach.spi.AttachProvider;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public final class JvmDiscovery {
    private JvmDiscovery() {
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            System.err.println(
                    "Usage: java --add-modules jdk.attach JvmDiscovery [name-fragment]");
            return;
        }

        String keyword = args.length == 1
                ? args[0].toLowerCase(Locale.ROOT)
                : "";

        List<VirtualMachineDescriptor> discovered =
                VirtualMachine.list();

        List<VirtualMachineDescriptor> matches = discovered.stream()
                .filter(vm -> vm.displayName()
                        .toLowerCase(Locale.ROOT)
                        .contains(keyword))
                .sorted(Comparator
                        .comparing((VirtualMachineDescriptor vm) ->
                                vm.provider().name())
                        .thenComparing(vm -> vm.provider().type())
                        .thenComparing(VirtualMachineDescriptor::id))
                .toList();

        System.out.printf("attachProviders=%d; discovered=%d; matches=%d%n",
                AttachProvider.providers().size(),
                discovered.size(),
                matches.size());

        for (VirtualMachineDescriptor vm : matches) {
            System.out.printf(
                    "id=%s | displayName=%s | provider=%s/%s%n",
                    vm.id(),
                    vm.displayName(),
                    vm.provider().name(),
                    vm.provider().type());
        }

        if (matches.isEmpty()) {
            System.out.println("(no matching JVM)");
        }
    }
}
~~~

Từ thư mục chứa tệp, biên dịch và chạy bằng JDK 17+:

~~~bash
javac --add-modules jdk.attach JvmDiscovery.java
java --add-modules jdk.attach JvmDiscovery
java --add-modules jdk.attach JvmDiscovery OrderService
~~~

**Cách đọc chương trình:**

1. `VirtualMachine.list()` lấy danh sách JVM khả kiến từ các provider.
2. Nếu không truyền đối số, `keyword` rỗng nên `contains("")` cho phép hiển thị mọi descriptor. Nếu truyền `OrderService`, chương trình chỉ giữ các descriptor có `displayName()` chứa đoạn tên này, không phân biệt hoa/thường theo `Locale.ROOT`.
3. `stream().sorted(...)` sắp xếp kết quả theo tên provider, loại provider rồi ID để dễ so sánh. Chương trình không thay đổi danh sách do API trả về.
4. `matches` có thể chứa 0, 1 hoặc nhiều mục. Kết quả 1 mục chỉ là **một ứng viên phù hợp bộ lọc**, không phải xác nhận chắc chắn đúng ứng dụng.
5. Không có lời gọi `VirtualMachine.attach(...)`, `loadAgent(...)` hay `detach()` vì chương trình này **chỉ khám phá**.

**Ví dụ minh họa định dạng đầu ra (giả định máy có 1 provider, 3 JVM khả kiến và 1 tên khớp):**

~~~text
attachProviders=1; discovered=3; matches=1
id=7421 | displayName=com.example.OrderService | provider=sun/socket
~~~

Số tiến trình, ID, display name, tên/type provider và thứ tự các JVM thực tế **phụ thuộc vào máy và thời điểm chạy**. Đây không phải stdout cố định để so sánh nguyên văn. Nếu không có mục nào khớp, chương trình in dòng `(no matching JVM)` sau dòng đếm; điều đó chưa đủ để kết luận ứng dụng không chạy.

### Vì sao ví dụ không tự động attach vào phần tử đầu tiên?

Một bộ lọc theo `displayName` có thể khớp hai bản sao cùng ứng dụng, hoặc chứa một tên tương tự. Chọn `matches.get(0)` rồi attach sẽ có nguy cơ nhắm nhầm JVM. Ứng dụng thực tế nên **liệt kê các ứng viên cùng ID/provider**, yêu cầu chọn hoặc xác minh mục tiêu bằng tiêu chí đáng tin hơn, sau đó kiểm tra lại trạng thái ngay trước hành động attach.

## 5. Ví dụ phân tích một kết quả khám phá

Giả sử có ba descriptor dạng:

| id | displayName | provider |
| --- | --- | --- |
| `7421` | `com.example.OrderService` | `sun/socket` |
| `7550` | `com.example.OrderService` | `sun/socket` |
| `8992` | `com.example.BatchWorker` | `sun/socket` |

Nếu lọc `OrderService` sẽ nhận **hai** mục: `7421` và `7550`. Việc hai descriptor cùng display name không chứng minh đây là cùng một tiến trình; có thể là hai JVM phục vụ hai instance hoặc hai môi trường. Với nhiều provider, một ID giống nhau cũng cần đi kèm tên/type hoặc chính đối tượng provider để hiểu đúng ngữ cảnh.

Một cách lựa chọn thận trọng:

- Dùng `displayName` để **tìm ứng viên**, không làm khóa duy nhất.
- Hiển thị `id` và `provider` cho người vận hành.
- Nếu ID là PID trên nền tảng đang dùng, đối chiếu thêm tiến trình OS hoặc metadata triển khai bằng công cụ phù hợp; đừng giả định mọi ID đều có thể đối chiếu như vậy.
- Khi có nhiều ứng viên, giải quyết sự nhập nhằng trước khi chuyển sang bước attach.
- Quét lại ngay trước thao tác ảnh hưởng mục tiêu, bởi tiến trình cũ có thể đã kết thúc hoặc PID được tái sử dụng.

Một descriptor được lấy từ lần quét trước **không giữ tiến trình còn sống**; đây là vấn đề quen thuộc của việc quan sát hệ thống đang thay đổi (*time-of-check vs. time-of-use*).

## 6. list() và attach() khác nhau ở đâu?

| Tiêu chí | `VirtualMachine.list()` | `VirtualMachine.attach(descriptor)` |
| --- | --- | --- |
| Đầu vào | Không có tham số | Một descriptor đã chọn |
| Kết quả | `List<VirtualMachineDescriptor>` | `VirtualMachine` đại diện kết nối đã attach |
| Mục đích | Khám phá JVM và đọc thông tin nhận diện | Kết nối vào JVM mục tiêu |
| Nạp agent | Không | Không tự nạp chỉ vì attach; cần thao tác riêng |
| Lỗi do permission/khả năng attach | Có thể ảnh hưởng tính khả kiến | Có thể gây lỗi attach trực tiếp |
| Bảo đảm từ bước trước | Không bảo đảm attach được | Phụ thuộc trạng thái thực tế và provider |

Có hai overload `VirtualMachine.attach(String id)` và `VirtualMachine.attach(VirtualMachineDescriptor descriptor)`. Ở bước tiếp theo của một công cụ dùng danh sách khám phá, overload nhận descriptor chuyển thao tác đến **provider đi kèm descriptor**, trong khi overload nhận chuỗi ID sẽ lần lượt thử các provider phù hợp. Bài này không thực hiện attach để tránh ảnh hưởng tới ứng dụng đang chạy.

Các lỗi như `AttachNotSupportedException` hoặc `IOException` là vấn đề của **bước attach**; việc `list()` có một descriptor không bảo đảm các lỗi đó sẽ không xảy ra. Nếu đã attach thành công trong chương trình khác thì cần có quy trình `detach()` khi hoàn tất, nhưng không có gì cần detach sau khi chỉ gọi `list()`.

## 7. Tại sao danh sách rỗng hoặc thiếu JVM?

Một số tình huống cần phân biệt:

| Quan sát | Cách diễn giải hợp lý | Hành động kiểm tra |
| --- | --- | --- |
| `attachProviders=0`, `discovered=0` | Không có provider để liệt kê; **chưa thể kết luận không có JVM** | Kiểm tra JDK/runtime và module `jdk.attach` |
| `attachProviders>0`, `discovered=0` | Provider tồn tại nhưng không thấy JVM nào | Kiểm tra tiến trình đang chạy, quyền và cơ chế visibility |
| `discovered>0`, `matches=0` | Có JVM khả kiến nhưng **không khớp từ khóa displayName** | Chạy không có từ khóa, kiểm tra tên thật |
| Có descriptor, attach về sau thất bại | Discovery và quyền/kỹ thuật attach là hai bước khác nhau | Kiểm tra quyền, provider tương thích, trạng thái JVM, cấu hình attach |
| Thấy tên giống nhau nhiều lần | Có nhiều ứng viên; tên hiển thị không duy nhất | So sánh ID/provider và xác minh từng tiến trình |
| Kết quả thay đổi liên tiếp | Tiến trình đến/đi trong thời gian quét | Quét lại và ghi nhận thời điểm |

**Các nguyên nhân môi trường có thể ảnh hưởng khả năng khám phá:**

- **JDK/JVM khác nhau:** provider được triển khai theo vendor, phiên bản, hệ điều hành hoặc cơ chế attach. Một provider không bắt buộc nhìn thấy mọi loại JVM.
- **Quyền hệ điều hành:** ứng dụng đang chạy dưới user khác hoặc bị hạn chế truy cập vào thông tin tiến trình/IPC; hành vi chi tiết phụ thuộc platform.
- **Container, PID namespace, filesystem namespace:** một JVM nhìn thấy từ host có thể không hiện diện với cùng ID hoặc không khả kiến từ công cụ đang chạy bên trong container.
- **Cơ chế attach của mục tiêu:** một số JVM có thể cấu hình vô hiệu hóa attach hoặc không hỗ trợ provider hiện tại. **Đừng suy ra ngược** rằng JVM không có trong `list()` chỉ vì attach của nó bị tắt; khám phá và attach có thể dùng các cơ chế kiểm tra khác nhau.
- **Vòng đời tiến trình:** JVM dừng hoặc khởi động giữa các lần gọi; PID có thể đổi hoặc được sử dụng lại.
- **Tên hiển thị:** JVM khả kiến nhưng `displayName()` không chứa tên class/JAR như bạn kỳ vọng, khiến bộ lọc bỏ sót.

Đừng dùng một `discovered=0` làm tín hiệu tuyệt đối cho hệ thống giám sát rằng "không còn dịch vụ Java chạy". Hãy kết hợp thêm bằng chứng từ runtime, công cụ OS hoặc kênh giám sát ứng dụng phù hợp.

## 8. So sánh với jps, jcmd và ProcessHandle

Ngoài ví dụ Java API trên, JDK thường cung cấp công cụ dòng lệnh hỗ trợ quan sát:

~~~bash
jps -l
jcmd -l
~~~

- `jps -l` hiển thị các JVM instrumented mà công cụ phát hiện được, thường kèm main class/JAR theo cách trình bày của `jps`.
- `jcmd -l` liệt kê JVM phục vụ thao tác diagnostic trên những nền tảng/JDK hỗ trợ.
- `ProcessHandle.allProcesses()` là API ở mức tiến trình OS, có thể liệt kê cả tiến trình không phải Java và bị ràng buộc bởi quyền truy cập hệ điều hành.
- `VirtualMachine.list()` trả **descriptor kèm attach provider** dưới dạng Java object để một công cụ có thể tiếp tục quy trình dựa trên Attach API.

Những công cụ/API này **không có hợp đồng trả cùng một tập tiến trình**. Nếu kết quả khác nhau, trước tiên kiểm tra quyền, JVM implementation, namespace, môi trường JDK và cơ chế liệt kê. Không giả định một số dòng tương đương trên mọi hệ điều hành.

## 9. Sai lầm thường gặp khi viết công cụ khám phá JVM

1. **Đồng nhất ID với PID số:** mã gọi `Long.parseLong(vm.id())` không portable. Với Attach API, ID phải được coi là chuỗi do provider quản lý.
2. **So sánh duy nhất `displayName()`:** hai instance có thể cùng tên. Đây là dữ liệu hiển thị, không phải định danh độc nhất.
3. **Chọn `findFirst()` trên kết quả `list()`:** thứ tự không được bảo đảm, và danh sách có thể thay đổi giữa các lần quét.
4. **Hiểu `list()` như hành động attach:** nó không gọi `loadAgent`, không tạo kết nối có thể thao tác, và không cần `detach`.
5. **Cho rằng có descriptor chắc chắn attach được:** target có thể thoát, không tương thích hoặc không cho phép kết nối.
6. **Ẩn hoàn toàn thông tin provider:** khi nhiều provider cùng tồn tại, thiếu provider khiến việc chọn đối tượng và xử lý lỗi khó giải thích.
7. **Hard-code `sun/socket`, một PID hoặc một tên main class:** những giá trị này không ổn định giữa máy, vendor và cách chạy.
8. **Đọc `discovered=0` là không có JVM:** cần phân biệt 0 provider, không có quyền visibility, không có mục tiêu và khác biệt môi trường.
9. **Ghi log `displayName` mà không kiểm soát:** tên hiển thị có thể phản ánh một phần thông tin khởi động, nên cân nhắc khi đưa nguyên văn vào log/public dashboard.
10. **Quét một lần rồi dùng mãi:** kết quả là ảnh chụp tại thời điểm liệt kê; hãy xác minh lại khi cần hành động tới JVM.

Đối với chương trình công cụ chạy định kỳ, hãy log **số provider**, **số descriptor phát hiện**, **số mục phù hợp bộ lọc** và thời điểm quét. Những số này giúp phân biệt vấn đề visibility với vấn đề filter, nhưng vẫn chưa thay thế kiểm tra attach hoặc kiểm tra sức khỏe ứng dụng.

## 10. Bài tập thực hành

**Bài 1.** Hai JVM có `displayName()` đều là `com.acme.App`, nhưng `id()` là `101` và `102`. Bộ lọc `displayName().contains("App")` trả về bao nhiêu phần tử? Có được tự động attach vào phần tử đầu tiên không?

**Bài 2.** `VirtualMachine.list()` trả danh sách rỗng; `AttachProvider.providers()` cũng rỗng. Bạn có thể kết luận không chạy ứng dụng Java nào không? Vì sao?

**Bài 3.** Một descriptor có `id() = "svc-A"`. Đoạn code nào có nguy cơ lỗi và vì sao: `System.out.println(vm.id())` hay `Long.parseLong(vm.id())`?

**Bài 4.** `VirtualMachine.list()` trả một descriptor, nhưng một công cụ khác gọi `VirtualMachine.attach(descriptor)` rồi nhận `AttachNotSupportedException`. Hai kết quả có mâu thuẫn contract API không?

**Bài 5.** Phân biệt việc dùng `VirtualMachineDescriptor`, `VirtualMachine` và `ProcessHandle` khi xây dựng danh sách chọn một tiến trình JVM.

### Đáp án và giải thích

1. Có **2** phần tử. Không chọn `findFirst()` chỉ vì tên trùng; cần xác minh ID/provider và đúng instance.
2. **Không**. Khi không có attach provider, API không có nguồn liệt kê; danh sách rỗng không chứng minh máy không có JVM.
3. `Long.parseLong("svc-A")` ném `NumberFormatException`. `id()` là chuỗi phụ thuộc triển khai, không nhất thiết là PID số.
4. **Không mâu thuẫn**. Liệt kê nghĩa là provider biết tới mục tiêu; attach thành công là điều kiện riêng, có thể thất bại.
5. `VirtualMachineDescriptor` dùng để nhận diện **ứng viên**, `VirtualMachine` biểu diễn **kết nối sau attach**, còn `ProcessHandle` cho thông tin ở mức **tiến trình OS** và không thay thế thông tin attach provider.

## 11. Nguồn tham khảo chính thức

- [Java 21: `VirtualMachine.list()` và `attach(...)`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachine.html) — contract của việc liệt kê và attach.
- [Java 21: `VirtualMachineDescriptor`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/VirtualMachineDescriptor.html) — ý nghĩa `id()`, `displayName()` và `provider()`.
- [Java 21: `AttachProvider`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.attach/com/sun/tools/attach/spi/AttachProvider.html) — nguồn liệt kê và việc không bảo đảm attach thành công.
- [Java 17: gói `com.sun.tools.attach`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.attach/com/sun/tools/attach/package-summary.html) — Attach API trong module `jdk.attach`.
