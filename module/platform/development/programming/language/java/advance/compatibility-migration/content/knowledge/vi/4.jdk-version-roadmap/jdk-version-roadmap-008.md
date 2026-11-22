# Nâng cấp JDK 21 lên 25: rà soát thay đổi tích lũy của các bản trung gian

Nâng cấp từ JDK 21 lên JDK 25 đi qua bốn bản phát hành tính năng: JDK 22, 23, 24 và 25. Mỗi bản mang theo thay đổi về API, ngôn ngữ, JVM, công cụ và hành vi runtime. Vì vậy, việc chỉ đọc ghi chú phát hành của JDK 25 có thể bỏ sót một thay đổi đã xuất hiện ở bản trung gian nhưng tác động trực tiếp đến ứng dụng.

JDK 22, 23 và 24 là các bản phát hành tính năng nằm giữa hai mốc 21 và 25. Nhiều tổ chức không triển khai production trên từng bản trung gian, nhưng vẫn cần hiểu các thay đổi tích lũy của chúng để xác định nguyên nhân khi build, test hoặc chạy trên JDK 25. JDK 25 là mốc LTS trong lịch hỗ trợ của nhiều nhà cung cấp; thời hạn hỗ trợ, bản vá và chính sách cập nhật vẫn phụ thuộc vào vendor và bản phân phối JDK mà tổ chức lựa chọn.

Bài học này xây dựng một lộ trình rà soát có hệ thống: nhận diện thay đổi theo từng release, đánh giá tác động đến mã nguồn và dependency, kiểm tra cấu hình JVM, sau đó xác minh ứng dụng trên JDK 25.

## 1. Phạm vi của một lần nâng cấp 21 lên 25

Một lần nâng cấp JDK có ít nhất bốn lớp tương thích cần xem xét:

1. **Tương thích mã nguồn:** mã có còn biên dịch được với compiler mới, API mới và các thay đổi trong ngôn ngữ hay không.
2. **Tương thích binary:** class file, thư viện, annotation processor, agent và công cụ bytecode có đọc hoặc nạp được định dạng và API mới hay không.
3. **Tương thích hành vi:** ứng dụng có còn hoạt động đúng khi JVM, garbage collector, thread scheduler, bảo mật hoặc thư viện chuẩn thay đổi hay không.
4. **Tương thích vận hành:** script khởi chạy, container image, tham số JVM, native library, monitoring và quy trình phát hành có còn phù hợp hay không.

Không phải mọi thay đổi trong JDK đều ảnh hưởng đến mọi ứng dụng. Chẳng hạn, một ứng dụng chỉ dùng Java thuần, không dùng Security Manager, không gọi JNI và không dùng ZGC có thể ít chịu tác động từ một số thay đổi runtime. Ngược lại, một hệ thống sử dụng thư viện native, framework dựa vào reflection sâu, agent instrumentation hoặc virtual thread cần kiểm tra kỹ hơn.

Hãy phân biệt ba khái niệm trong kế hoạch:

- **JDK dùng để build:** compiler và công cụ được dùng để tạo artifact.
- **JDK dùng để test:** runtime chạy unit test, integration test và kiểm tra tương thích.
- **JDK dùng để production:** runtime thực sự chạy ứng dụng.

Ba môi trường này có thể dùng cùng một phiên bản, nhưng không nên mặc định như vậy. Ví dụ, có thể build bằng JDK 25 nhưng dùng tùy chọn release 21 để tạo bytecode và giới hạn API ở Java 21, sau đó chạy thử trên cả JDK 21 và JDK 25. Nếu sản phẩm chỉ hỗ trợ JDK 25, có thể chuyển cả build target và runtime lên 25 sau khi xác nhận dependency.

## 2. Bản đồ thay đổi từ JDK 22 đến JDK 25

Bảng dưới đây tập trung vào các thay đổi tiêu biểu có thể ảnh hưởng đến migration. Đây không phải danh sách toàn bộ JEP của từng bản phát hành; hãy dùng nó để định hướng kiểm kê và kiểm thử.

| Bản phát hành | Thay đổi đáng chú ý | Tác động cần rà soát |
|---|---|---|
| JDK 22 | Foreign Function & Memory API trở thành API chính thức; unnamed variables và patterns được hoàn thiện; nhiều API ngôn ngữ và công cụ tiếp tục ở trạng thái preview | Mã native interop, thư viện sử dụng Unsafe, source code dùng preview feature, công cụ phân tích bytecode |
| JDK 23 | Generational ZGC trở thành chế độ mặc định; các phương thức truy cập bộ nhớ của sun.misc.Unsafe bị deprecate for removal; nhiều tính năng ngôn ngữ tiếp tục preview | Cấu hình GC, dependency native/low-level, log cảnh báo, framework và plugin |
| JDK 24 | Class-File API và Stream Gatherers được hoàn thiện; Security Manager bị vô hiệu hóa vĩnh viễn; ZGC bỏ chế độ non-generational; virtual thread không còn bị pin chỉ vì dùng synchronized; JNI và Unsafe có thêm cảnh báo | Security Manager, native access, GC flags, virtual-thread diagnostics, thư viện thao tác bytecode |
| JDK 25 | Scoped Values, Module Import Declarations, Compact Source Files và Flexible Constructor Bodies trở thành tính năng chính thức; Applet API và các port 32-bit x86 còn lại bị loại bỏ; có cảnh báo về việc sửa final field bằng reflection | Framework dùng reflection, mã applet cũ, máy 32-bit, source code và thư viện phụ thuộc API bị loại bỏ |

Khi đọc ghi chú phát hành, hãy phân loại từng thay đổi theo ba nhóm:

- **Breaking hoặc removal:** API, port hoặc khả năng runtime bị loại bỏ hay không còn hoạt động.
- **Behavioral hoặc default change:** API còn tồn tại nhưng hành vi, mặc định hoặc cảnh báo đã thay đổi.
- **New capability:** tính năng mới, thường không gây lỗi nếu ứng dụng không sử dụng; chỉ cần đánh giá khi muốn áp dụng.

Cách phân loại này giúp tránh nâng cấp theo kiểu bật tất cả tính năng mới cùng lúc. Trước hết hãy làm cho ứng dụng chạy ổn trên JDK 25; sau đó mới quyết định có áp dụng API hoặc tối ưu hóa mới hay không.

## 3. JDK 22: API native chính thức và nhiều tính năng preview

### 3.1. Foreign Function & Memory API trở thành API chính thức

JEP 454 hoàn thiện Foreign Function & Memory API (FFM). API này cung cấp cơ chế Java để làm việc với bộ nhớ ngoài JVM và gọi hàm native mà không nhất thiết phải viết JNI wrapper thủ công.

Điểm quan trọng khi migration là các phiên bản FFM trước JDK 22 đã trải qua nhiều vòng incubator hoặc preview và có thể khác đáng kể về package, kiểu dữ liệu, vòng đời bộ nhớ và cách khai báo lời gọi native. Nếu ứng dụng hoặc thư viện đang dùng bản thử nghiệm cũ, không nên chỉ đổi JDK rồi giả định mã sẽ tương thích. Cần nâng cấp thư viện hoặc chuyển code sang API chính thức.

Ví dụ dưới đây minh họa cấp phát bộ nhớ ngoài heap với Arena:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ForeignMemoryExample {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(100);

            segment.set(ValueLayout.JAVA_INT, 0, 42);
            int value = segment.get(ValueLayout.JAVA_INT, 0);

            System.out.println(value);
        }
    }
}
```

Arena quản lý vòng đời vùng nhớ. Khi arena đóng, vùng nhớ được giải phóng theo cơ chế của API. Điều này khác với việc giữ một địa chỉ native tùy ý và tự chịu trách nhiệm quản lý lifetime. Khi chuyển từ JNI hoặc Unsafe sang FFM, cần xác định rõ ai sở hữu bộ nhớ, khi nào bộ nhớ hết hiệu lực và liệu dữ liệu có thể được truy cập đồng thời hay không.

FFM không tự động thay thế mọi trường hợp JNI. Những thư viện cần callback phức tạp, tích hợp native lâu đời hoặc phụ thuộc ABI riêng vẫn cần kiểm tra kỹ. Tuy nhiên, với các lời gọi hàm native và thao tác bộ nhớ phù hợp, FFM là lựa chọn chuẩn của Java để giảm phụ thuộc vào API nội bộ.

### 3.2. Unnamed Variables and Patterns

JEP 456 hoàn thiện unnamed variables và patterns. Ký hiệu gạch dưới có thể được dùng cho biến hoặc pattern mà chương trình không cần sử dụng giá trị.

Ví dụ:

```java
try {
    process();
} catch (IOException _) {
    logFailure();
}
```

Tính năng này chủ yếu cải thiện khả năng đọc mã và loại bỏ biến không dùng. Khi nâng compiler, hãy kiểm tra source level và các thư viện phân tích mã nếu chúng tự xử lý cú pháp Java. Một parser cũ có thể không nhận ra cú pháp mới dù compiler của JDK đã hỗ trợ.

### 3.3. Class-File API ở trạng thái preview

JEP 457 đưa Class-File API vào giai đoạn preview. API này hướng đến việc đọc, tạo và biến đổi class file bằng API chuẩn của JDK.

Nếu dự án sử dụng ASM, Byte Buddy, Javassist hoặc công cụ tự sửa bytecode, cần kiểm tra phiên bản thư viện có hỗ trợ class file và JDK mới hay không. Class-File API preview không có nghĩa các thư viện hiện tại phải chuyển ngay sang API đó. Đây là cơ hội để đánh giá hướng phát triển dài hạn, không phải lý do để thay toàn bộ công cụ bytecode trong cùng một lần migration.

Class-File API chỉ trở thành API chính thức ở JDK 24. Vì vậy, mã thử nghiệm viết trên JDK 22 cần được chuyển theo phiên bản API cuối cùng nếu dự án quyết định sử dụng.

### 3.4. Stream Gatherers và các tính năng đồng thời ở trạng thái preview

JDK 22 đưa Stream Gatherers vào preview qua JEP 461. Gatherer cho phép định nghĩa thao tác trung gian tùy chỉnh trong Stream API. Tính năng này tiếp tục thay đổi trước khi trở thành chính thức ở JDK 24.

Structured Concurrency và Scoped Values cũng tiếp tục ở trạng thái preview trong JDK 22. Một số tính năng ngôn ngữ khác như constructor body linh hoạt, lớp được khai báo ngầm và instance main method cũng có các vòng preview.

Khi kiểm tra source code, hãy tìm:

- Tùy chọn **--enable-preview** trong cấu hình compiler và runtime.
- Annotation hoặc API thuộc package preview.
- Cấu hình test, IDE và build plugin có bật preview.
- Thư viện nội bộ đóng gói class file được biên dịch bằng preview feature.

Preview feature được gắn với release cụ thể. Class file hoặc mã nguồn dùng preview của JDK 21 không thể được coi là tự động tương thích với preview của JDK 25. Nếu production không có chủ trương chấp nhận API preview, hãy loại bỏ hoặc thay thế chúng trước khi hoàn tất migration.

### 3.5. Các thay đổi về công cụ và tài liệu

JEP 458 cho phép khởi chạy chương trình Java nhiều file nguồn trực tiếp từ launcher trong một số trường hợp mà không cần biên dịch thủ công trước. Đây là cải tiến trải nghiệm phát triển và script; không làm thay đổi cách đóng gói ứng dụng production thông thường.

JEP 467 hỗ trợ Markdown trong documentation comment. Nếu dự án có pipeline tạo Javadoc hoặc công cụ kiểm tra comment, hãy xác nhận phiên bản công cụ xử lý đúng định dạng mới. Đây thường là thay đổi có tác động thấp đến runtime.

## 4. JDK 23: thay đổi mặc định của ZGC và cảnh báo Unsafe

### 4.1. Generational ZGC trở thành mặc định

JEP 474 đặt Generational ZGC làm chế độ mặc định khi chọn ZGC. Generational ZGC phân chia đối tượng theo tuổi để tận dụng đặc điểm rằng phần lớn đối tượng thường sống trong thời gian ngắn.

JDK 21 đã có Generational ZGC, nhưng người vận hành phải chủ động bật bằng tùy chọn tương ứng. Từ JDK 23, ứng dụng chọn ZGC sẽ sử dụng chế độ generational theo mặc định. Điều này có nghĩa một cấu hình JVM cũ có thể tạo ra hành vi GC khác sau khi đổi JDK, ngay cả khi không sửa code.

Cần kiểm tra:

- Script khởi chạy có bật **-XX:+UseZGC** hay không.
- Có tùy chọn bật/tắt generational mode được giữ lại từ JDK 21 hay không.
- Dashboard có đang giả định tên hoặc cấu trúc log GC cũ hay không.
- Heap size, allocation rate, pause time và throughput thay đổi thế nào trên workload thật.
- Các thư viện hoặc agent có dựa vào chi tiết triển khai GC hay không.

Đến JDK 24, chế độ ZGC non-generational bị loại bỏ. Vì vậy, cấu hình cũ cố yêu cầu chế độ đó phải được rà soát và loại bỏ. Đừng sao chép nguyên trạng toàn bộ JVM flags từ JDK 21 sang JDK 25; mỗi flag cần được xác minh theo runtime đích.

### 4.2. Các phương thức truy cập bộ nhớ của sun.misc.Unsafe bị deprecate for removal

JEP 471 deprecate for removal các phương thức truy cập bộ nhớ trong **sun.misc.Unsafe**. Đây là cảnh báo quan trọng đối với framework, serializer, thư viện hiệu năng cao, công cụ concurrency và mã native interop.

Không phải toàn bộ lớp Unsafe bị loại bỏ ngay lập tức. Phạm vi thay đổi tập trung vào các phương thức memory-access được chỉ định trong JEP. Tuy nhiên, một dependency vẫn gọi các phương thức đó có thể tiếp tục chạy nhưng tạo cảnh báo, rồi gặp hạn chế mạnh hơn trong các bản JDK tiếp theo.

Hướng xử lý tùy theo mục đích:

| Nhu cầu hiện tại | Hướng thay thế nên xem xét |
|---|---|
| Truy cập field hoặc array theo kiểu an toàn | VarHandle |
| Cấp phát và truy cập bộ nhớ ngoài JVM | Foreign Function & Memory API |
| Gọi hàm native | Foreign Function & Memory API hoặc JNI được quản lý rõ ràng |
| Thao tác bytecode hoặc runtime internals | API chuẩn, Class-File API hoặc thư viện đã cập nhật |
| Dùng Unsafe thông qua dependency bên thứ ba | Nâng cấp dependency lên phiên bản đã xử lý cảnh báo |

Không nên tự viết một lớp wrapper quanh Unsafe rồi coi vấn đề đã được giải quyết. Wrapper vẫn phụ thuộc vào API bị deprecate. Hãy xác định thư viện nào gọi các phương thức đó, kiểm tra roadmap của nhà cung cấp và lên kế hoạch thay thế.

### 4.3. Rà soát thư viện phụ thuộc và source compatibility

JDK 23 tiếp tục đưa các tính năng ngôn ngữ vào preview, trong đó có primitive types trong pattern, **instanceof** và **switch**; module import declarations; flexible constructor bodies; cùng các tính năng về structured concurrency và scoped values.

Các tính năng này có thể thay đổi giữa các preview. Nếu mã nguồn của dự án sử dụng chúng, cần kiểm tra lại theo đúng release. Nếu chỉ sử dụng Java 21 language level, phần lớn ứng dụng không phải thay code vì những preview này.

Đối với dependency, cần kiểm tra những thư viện tạo hoặc phân tích bytecode, annotation processor, compiler plugin, agent và framework dựa vào reflection. Thư viện có thể vẫn được biên dịch từ trước nhưng chưa chắc hoạt động đúng trên runtime mới.

## 5. JDK 24: thay đổi lớn về Security Manager, native access và runtime

### 5.1. Security Manager bị vô hiệu hóa vĩnh viễn

JEP 486 vô hiệu hóa Security Manager vĩnh viễn. Ứng dụng không thể tiếp tục dựa vào cơ chế này để áp dụng permission policy trong JVM.

Nếu ứng dụng hoặc thư viện gọi **System.setSecurityManager**, việc bật Security Manager bằng tùy chọn khởi động cũ hoặc trông đợi các permission check được thực thi, hãy xem đây là hạng mục migration bắt buộc. Việc gọi **System.setSecurityManager** không còn thiết lập được Security Manager và có thể ném **UnsupportedOperationException**; **System.getSecurityManager** không cung cấp một Security Manager đang hoạt động.

Tìm kiếm trong mã nguồn và cấu hình:

- **System.setSecurityManager(...)** và **System.getSecurityManager()**.
- **java.security.Policy** và file policy cũ.
- **SecurityManager** tùy chỉnh.
- Tùy chọn **-Djava.security.manager** trong script.
- Framework hoặc thư viện dựa vào permission check của Security Manager.

Security Manager không phải cơ chế sandbox phù hợp cho ứng dụng mới. Nếu mục tiêu là giới hạn quyền của tiến trình, hãy chuyển kiểm soát sang ranh giới hệ điều hành và hạ tầng: tài khoản service riêng, quyền filesystem tối thiểu, container isolation, network policy và quyền truy cập secret. Những cơ chế này cần được thiết kế theo threat model của hệ thống, không thể thay bằng một phép đổi tên API.

### 5.2. JNI và native access bắt đầu có cảnh báo

JEP 472 chuẩn bị hạn chế việc sử dụng JNI. JDK 24 cảnh báo khi ứng dụng thực hiện thao tác native access trong trường hợp module chưa khai báo quyền tương ứng. Mục tiêu là làm rõ những điểm chương trình vượt ra khỏi ranh giới an toàn của JVM và chuẩn bị cho các bản phát hành có chính sách chặt hơn.

Nếu ứng dụng dùng JNI hoặc thư viện tải native library, cần:

1. Kiểm kê nơi gọi **System.load**, **System.loadLibrary** và các native method.
2. Xác định module sở hữu lời gọi native access.
3. Nâng cấp thư viện native và wrapper để hỗ trợ cơ chế cấp quyền hiện hành.
4. Cấu hình quyền native access rõ ràng cho module cần thiết.
5. Theo dõi warning trên JDK 24 và xác nhận hành vi trên JDK 25.

Với ứng dụng classpath chưa chia thành named module, tùy chọn **--enable-native-access=ALL-UNNAMED** có thể được dùng để cấp native access cho unnamed modules. Với ứng dụng modular, chỉ định module cần quyền, ví dụ **--enable-native-access=com.example.nativebridge**. Hãy cấp quyền đúng phạm vi thay vì bật rộng cho mọi module nếu kiến trúc cho phép giới hạn.

Tùy chọn này không biến một native library sai kiến trúc hoặc sai ABI thành tương thích. Nó chỉ giải quyết quyền truy cập native theo cơ chế của JVM.

### 5.3. ZGC loại bỏ chế độ non-generational

JEP 490 loại bỏ chế độ ZGC không generational. Đây là bước tiếp theo sau khi generational mode trở thành mặc định trong JDK 23.

Nếu cấu hình triển khai từng dùng tùy chọn tắt generational ZGC, cần bỏ cấu hình đó và xác nhận JVM đích khởi động bình thường. Kiểm tra toàn bộ nơi lưu JVM flags: Dockerfile, Helm chart, systemd unit, script, biến môi trường, pipeline và cấu hình service manager.

Không đánh giá GC chỉ bằng một lần chạy benchmark ngắn. Hãy so sánh trên workload có allocation rate, live set, concurrency và thời gian chạy gần với production.

### 5.4. Virtual thread không còn bị pin chỉ vì synchronized

JEP 491 thay đổi cách virtual thread tương tác với monitor. Trước JDK 24, virtual thread có thể bị pin vào carrier thread khi đi vào một số đoạn code dùng **synchronized**; nếu đoạn đó thực hiện blocking operation, khả năng mở rộng của ứng dụng có thể bị ảnh hưởng.

Từ JDK 24, virtual thread có thể giải phóng carrier trong các trường hợp monitor này, nên việc dùng synchronized tự nó không còn gây kiểu pinning cũ. Đây là thay đổi có lợi cho ứng dụng sử dụng virtual thread, nhưng không có nghĩa mọi nguyên nhân pinning đều biến mất. Native method và một số thao tác ngoài JVM vẫn cần được kiểm tra.

Nếu code trước đây được viết lại từ synchronized sang **ReentrantLock** chỉ để né monitor pinning, hãy đánh giá lại thiết kế bằng benchmark và profiling. Không cần thay đổi hàng loạt nếu cấu trúc hiện tại đã đúng. Đồng thời, monitor contention vẫn có chi phí: loại bỏ pinning không đồng nghĩa khóa cạnh tranh cao sẽ trở nên miễn phí.

### 5.5. Unsafe có cảnh báo runtime

Sau khi các phương thức memory-access của **sun.misc.Unsafe** bị deprecate for removal trong JDK 23, JEP 498 bổ sung cảnh báo khi chúng được sử dụng. Đây là tín hiệu để tìm dependency còn sử dụng API này.

Cảnh báo có thể xuất hiện từ thư viện bên thứ ba thay vì code nghiệp vụ. Vì vậy, hãy thu thập stack trace hoặc thông tin caller khi có thể, sau đó nâng cấp dependency hoặc thay thế phần tích hợp. Không nên tắt cảnh báo trước khi xác định được nguồn gọi và kế hoạch xử lý.

### 5.6. Class-File API và Stream Gatherers trở thành API chính thức

Hai thay đổi đáng chú ý trong JDK 24:

- JEP 484 hoàn thiện Class-File API, cung cấp API chuẩn để đọc, tạo và biến đổi class file.
- JEP 485 hoàn thiện Stream Gatherers, cho phép xây dựng các phép biến đổi trung gian tùy chỉnh cho Stream.

Nếu dự án đã thử các preview trước đó, hãy chuyển sang API chính thức và kiểm tra thay đổi chữ ký, package, semantics và cách cấu hình compiler. Nếu dự án chưa dùng các tính năng này, không cần chuyển đổi chỉ vì chúng đã trở thành chính thức.

Với Class-File API, ưu tiên kiểm tra thư viện bytecode và agent instrumentation. Các công cụ này thường nhạy cảm với class file version, cấu trúc bytecode và thay đổi trong JVM. Một ứng dụng có thể khởi động bình thường nhưng thất bại khi agent biến đổi class hoặc framework tạo proxy.

### 5.7. Ahead-of-Time Class Loading & Linking

JEP 483 giới thiệu cơ chế Ahead-of-Time Class Loading & Linking nhằm giảm chi phí khởi động và warm-up trong các trường hợp phù hợp. Cơ chế này có thể hữu ích cho ứng dụng khởi động thường xuyên, dịch vụ serverless hoặc workload cần thời gian sẵn sàng ngắn.

Đây là hướng tối ưu hiệu năng, không phải yêu cầu bắt buộc để chạy trên JDK 24 hoặc 25. Trước khi áp dụng, hãy đo startup time và memory footprint ở baseline, xây dựng cache theo đúng ứng dụng và runtime, rồi so sánh trong môi trường triển khai. Không dùng cache được tạo từ một cấu hình không tương thích với runtime đích.

### 5.8. Một số thay đổi khác của JDK 24

JDK 24 cũng bổ sung các thuật toán mật mã hậu lượng tử như ML-KEM và ML-DSA trong thư viện mật mã của JDK. Nếu ứng dụng lựa chọn provider hoặc thuật toán theo tên cụ thể, hãy kiểm tra danh sách provider, chính sách bảo mật và khả năng tương tác với hệ thống đối tác. Việc bổ sung thuật toán mới không đồng nghĩa hệ thống tự động chuyển sang dùng thuật toán đó.

JDK 24 loại bỏ Windows 32-bit x86 port. Nếu tổ chức còn máy trạm, runner hoặc thiết bị triển khai 32-bit, hãy xác định lại kiến trúc được hỗ trợ và lập kế hoạch chuyển sang nền tảng 64-bit phù hợp.

## 6. JDK 25: mốc đích và các thay đổi cần xử lý

### 6.1. Những tính năng ngôn ngữ và API trở thành chính thức

JDK 25 hoàn thiện một số tính năng đã trải qua nhiều vòng preview:

| Tính năng | Trạng thái ở JDK 25 | Ý nghĩa |
|---|---|---|
| Scoped Values | Chính thức (JEP 506) | Truyền dữ liệu theo phạm vi thực thi, phù hợp với một số mô hình đồng thời |
| Module Import Declarations | Chính thức (JEP 511) | Import các module để giảm khai báo import rời rạc trong source file |
| Compact Source Files and Instance Main Methods | Chính thức (JEP 512) | Viết chương trình nhỏ với ít cấu trúc khai báo hơn |
| Flexible Constructor Bodies | Chính thức (JEP 513) | Cho phép thực hiện một số thao tác trước lời gọi constructor của superclass |

Các tính năng này không bắt buộc phải áp dụng trong ứng dụng hiện có. Nếu mã nguồn đã dùng preview của các bản trước, cần đối chiếu API cuối cùng và bỏ tùy chọn preview khi chuyển sang phiên bản chính thức. Nếu ứng dụng không dùng chúng, có thể giữ nguyên source style hiện tại.

Structured Concurrency vẫn là preview trong JDK 25. Primitive types trong patterns, **instanceof** và **switch** cũng tiếp tục ở trạng thái preview. Vector API vẫn là incubator. Không nên coi các API này là hợp đồng ổn định cho production nếu dự án chưa chấp nhận rủi ro thay đổi giữa các release.

### 6.2. Applet API bị loại bỏ

JEP 504 loại bỏ Applet API. Các ứng dụng hoặc thư viện còn tham chiếu **java.applet** có thể không biên dịch được trên JDK 25. Đây thường là dấu vết của phần mềm desktop hoặc web cũ, plugin trình duyệt đã lỗi thời, hoặc thư viện chưa được bảo trì.

Tìm các tham chiếu như:

- **java.applet.Applet**.
- **AppletContext**, **AppletStub** và các kiểu liên quan.
- Code khởi tạo hoặc truyền dữ liệu theo lifecycle của applet.
- Dependency cũ chỉ còn tồn tại để hỗ trợ applet.

Nếu chức năng vẫn cần thiết, hãy xác định mô hình triển khai thay thế như ứng dụng web, desktop application hoặc service. Chỉ xóa import để làm build qua không đủ nếu nghiệp vụ vẫn phụ thuộc lifecycle của applet.

### 6.3. Các port 32-bit x86 còn lại bị loại bỏ

Sau khi Windows 32-bit x86 bị loại bỏ ở JDK 24, JDK 25 tiếp tục loại bỏ port 32-bit x86 còn lại. Môi trường chạy Java 32-bit cần được xem là một hạng mục tương thích riêng, không chỉ là thay đổi JDK.

Kiểm kê:

- Máy chủ hoặc thiết bị còn chạy OS 32-bit.
- Runner CI, máy build và môi trường kiểm thử.
- Native library chỉ có binary 32-bit.
- Script cài đặt hoặc package manager tải JDK theo kiến trúc cũ.
- Giới hạn bộ nhớ hoặc phần mềm bên ngoài yêu cầu process 32-bit.

Nếu sản phẩm còn phụ thuộc 32-bit, cần chuyển cả JVM, native dependency và hệ điều hành sang tổ hợp 64-bit được hỗ trợ. Việc chỉ thay JDK có thể không giải quyết được dependency native hoặc hệ điều hành đã hết hỗ trợ.

### 6.4. Chuẩn bị cho việc hạn chế sửa final field bằng reflection

JEP 500 chuẩn bị làm cho từ khóa **final** có ý nghĩa chặt chẽ hơn đối với field. JDK 25 cảnh báo về việc dùng deep reflection để sửa final field trong những trường hợp không còn được khuyến khích và chuẩn bị cho các hạn chế mạnh hơn trong tương lai.

Các framework serialization, dependency injection, ORM, mocking và thư viện cấu hình có thể dùng reflection để ghi vào field sau khi object đã được tạo. Nếu những framework đó sửa final field, hãy kiểm tra warning trên JDK 25 và nâng cấp lên phiên bản hỗ trợ cách khởi tạo phù hợp.

Hướng thiết kế nên ưu tiên:

- Khởi tạo object qua constructor hoặc factory.
- Dùng API chính thức của framework thay cho reflection tự sửa field.
- Dùng serialization mechanism được thư viện hỗ trợ.
- Giữ final field bất biến sau khi object được tạo.
- Chỉ bật quyền đặc biệt cho phần code thật sự cần, theo chính sách JVM và phạm vi module phù hợp.

Không nên tự ý loại bỏ final trên mọi field để tránh warning. Hãy xác định framework nào cần sửa field, vì thay đổi đó có thể làm suy yếu invariant và thread-safety của object.

### 6.5. Thay đổi về garbage collection và object layout

JDK 25 có một số cải tiến về hiệu năng và GC cần được đánh giá bằng workload thực tế:

- **Compact Object Headers (JEP 519):** đưa ra cơ chế giảm kích thước object header trong các cấu hình hỗ trợ. Đây là thay đổi ở mức layout của object; hãy kiểm tra thư viện phụ thuộc vào chi tiết bộ nhớ nội bộ, agent và công cụ phân tích heap trước khi bật.
- **Generational Shenandoah (JEP 521):** bổ sung chế độ generational cho Shenandoah. Chỉ xem xét khi hệ thống sử dụng hoặc dự định thử collector này.
- **G1 throughput improvements (JEP 522):** cải thiện throughput bằng cách giảm một số điểm đồng bộ hóa. Kết quả thực tế phụ thuộc workload, heap và cấu hình.
- **AOT command-line ergonomics và method profiling (JEP 514, JEP 515):** giúp quy trình sử dụng dữ liệu ahead-of-time thuận tiện hơn và hỗ trợ tối ưu warm-up.

Các tính năng này là cơ hội tối ưu sau khi migration ổn định. Đừng bật đồng thời nhiều thay đổi GC, object layout và AOT rồi kết luận hiệu năng tăng hoặc giảm do riêng JDK. Hãy thay đổi từng nhóm, đo cùng một workload và lưu lại cấu hình JVM chính xác.

### 6.6. JFR và mật mã

JDK 25 tiếp tục mở rộng khả năng quan sát bằng Java Flight Recorder, bao gồm CPU-time profiling, cooperative sampling và method timing/tracing. Những cải tiến này hữu ích khi chẩn đoán CPU, latency và hoạt động method. Hãy xác nhận công cụ phân tích JFR mà đội vận hành sử dụng có hỗ trợ event mới.

JDK 25 cũng bổ sung Key Derivation Function API (JEP 510). Nếu ứng dụng có nhu cầu dẫn xuất khóa, hãy đánh giá API chuẩn này cùng chính sách quản lý khóa của hệ thống. Không tự thay đổi thuật toán, key size hoặc quy trình lưu trữ secret chỉ vì JDK có API mới.

## 7. Những điểm cần kiểm tra xuyên suốt cả bốn bản trung gian

### 7.1. API bị loại bỏ, deprecate hoặc thay đổi quyền sử dụng

Lập danh sách các API có vòng đời đặc biệt. Một API được đánh dấu deprecated không có nghĩa đã bị xóa ngay, nhưng cảnh báo **forRemoval** là tín hiệu cần có kế hoạch thay thế.

Ưu tiên kiểm tra:

| Khu vực | Thay đổi trong lộ trình 21 → 25 | Việc cần làm |
|---|---|---|
| Security Manager | Bị vô hiệu hóa vĩnh viễn ở JDK 24 | Tìm code và cấu hình còn bật hoặc kiểm tra permission |
| Applet API | Bị loại bỏ ở JDK 25 | Tìm dependency và source tham chiếu java.applet |
| sun.misc.Unsafe | Memory-access methods deprecate for removal ở 23, có cảnh báo runtime ở 24 | Xác định caller, nâng cấp hoặc chuyển sang API chuẩn |
| JNI/native access | JDK 24 bắt đầu cảnh báo và chuẩn bị siết quyền | Kiểm kê native call và khai báo quyền cho module cần thiết |
| Final field reflection | JDK 25 cảnh báo để chuẩn bị hạn chế trong tương lai | Nâng cấp framework và bỏ cách sửa final field không được hỗ trợ |
| 32-bit x86 | Các port bị loại bỏ trong JDK 24 và 25 | Kiểm tra OS, JVM, runner và native dependency |

Ngoài các thay đổi trên, hãy chạy công cụ phân tích trên artifact và dependency để tìm internal JDK API. Những package như **sun.*** hoặc **com.sun.*** không phải lúc nào cũng là API công khai ổn định. Nếu ứng dụng phụ thuộc vào chúng, cần xác định API thay thế hoặc nâng cấp thư viện sở hữu phần phụ thuộc đó.

### 7.2. Preview, incubator và API chính thức

Preview và incubator có mục đích cho phép thử nghiệm, thu thập phản hồi và thay đổi thiết kế trước khi ổn định. Chúng không phải cam kết tương thích lâu dài.

Trong lộ trình 21 → 25, một số tính năng đi qua nhiều vòng preview trước khi trở thành chính thức, ví dụ Scoped Values, Module Import Declarations, Flexible Constructor Bodies và một số tính năng source file đơn giản. Một số tính năng khác vẫn preview hoặc incubator ở JDK 25.

Quy tắc khi migration:

1. Tìm mọi nơi bật **--enable-preview**.
2. Xác định source code và class file thực sự phụ thuộc preview feature nào.
3. Kiểm tra trạng thái của tính năng ở JDK 25: final, preview tiếp tục hay không còn trong release.
4. Nếu đã final, chuyển code sang API cuối cùng và bỏ cấu hình preview nếu không còn cần.
5. Nếu vẫn preview, chỉ giữ khi dự án chấp nhận thay đổi API và có kế hoạch cập nhật theo release.
6. Nếu tính năng đã rút khỏi release, thay bằng API ổn định hoặc thiết kế khác.

Không nên bật **--enable-preview** toàn cục chỉ để làm một module thử nghiệm biên dịch được. Tách source set hoặc module thử nghiệm để phạm vi preview được kiểm soát.

### 7.3. Bytecode và class-file version

Mỗi release Java có class-file version tương ứng. JDK 21 tạo class file major version 65; JDK 22 là 66; JDK 23 là 67; JDK 24 là 68; JDK 25 là 69.

Một runtime mới thường có thể chạy bytecode cũ nếu các API mà code sử dụng còn tương thích. Runtime cũ không thể mặc nhiên chạy class file được biên dịch cho release mới. Vì vậy, phải xác định rõ phiên bản tối thiểu mà sản phẩm hỗ trợ.

Dùng **--release** để khóa đồng thời source compatibility, bytecode target và tập API chuẩn được phép dùng:

```shell
javac --release 21 -d out src/com/example/Main.java
```

Nếu build bằng JDK 25 nhưng muốn artifact tiếp tục chạy trên Java 21, giữ **--release 21**. Nếu sản phẩm chuyển hẳn sang Java 25, đặt release target là 25 sau khi dependency và runtime đã được xác nhận.

Không chỉ dùng source và target riêng lẻ rồi cho rằng đã giới hạn API. **--release** giúp compiler áp dụng tập API của release đích, giảm nguy cơ vô tình gọi API mới trong khi vẫn tạo bytecode cũ.

### 7.4. Build tool, plugin và thư viện bên thứ ba

Nâng cấp runtime có thể làm lộ vấn đề trong công cụ build trước khi code ứng dụng được chạy. Hãy kiểm tra các thành phần:

- Maven hoặc Gradle wrapper và plugin compiler.
- Annotation processor như Lombok hoặc processor tự viết.
- Test engine, mocking framework và thư viện tạo proxy.
- Bytecode library như ASM, Byte Buddy hoặc Javassist.
- Code coverage, static analysis, mutation testing và security scanning.
- Framework web, DI, ORM, logging và serialization.
- JDBC driver, database client, message broker client.
- Java agent, profiler, APM và monitoring agent.
- Native Image hoặc toolchain đặc thù nếu dự án có sử dụng.

Không nên chỉ cập nhật JDK mà giữ nguyên mọi plugin nhiều năm tuổi. Ngược lại, cũng không cần nâng cấp toàn bộ dependency không liên quan trong cùng một thay đổi. Xác định phiên bản tối thiểu hỗ trợ JDK 25, cập nhật nhóm có ràng buộc trực tiếp, sau đó chạy test để tách nguyên nhân.

Kiểm tra tài liệu hỗ trợ JDK của nhà cung cấp dependency. Một thư viện có thể biên dịch được nhưng chưa chắc hoạt động đúng trên runtime mới, hoặc có thể dùng reflection/native access cần cấu hình bổ sung.

### 7.5. Reflection, instrumentation và class loading

Framework Java thường dùng reflection để tạo proxy, inject dependency, serialize object hoặc gọi method động. Agent có thể biến đổi bytecode lúc khởi động. Các cơ chế này nhạy cảm với:

- Strong encapsulation của module.
- Quyền mở package qua **--add-opens** hoặc xuất package qua **--add-exports**.
- Thay đổi final-field mutation.
- Class-file version và bytecode attributes.
- Cách JVM nạp class và link class.
- Quyền native access nếu agent gọi JNI.

Không nên thêm hàng loạt **--add-opens** để che mọi lỗi. Hãy đọc warning, xác định module và package cần mở, kiểm tra bản cập nhật framework, rồi cấp quyền nhỏ nhất cần thiết. Những tùy chọn mở package rộng có thể che giấu dependency vào internal API và làm tăng chi phí nâng cấp sau này.

### 7.6. Threading và concurrency

Nếu ứng dụng dùng virtual thread, hãy kiểm tra cả hành vi blocking, monitor, native call và thread-local data. JDK 24 cải thiện pinning khi dùng synchronized, nhưng ứng dụng vẫn có thể gặp vấn đề do lock contention, pool giới hạn, native call kéo dài hoặc tài nguyên bên ngoài.

Nếu đang thử Structured Concurrency hoặc Scoped Values từ preview, cần kiểm tra đúng API final ở JDK 25. Scoped Values đã trở thành chính thức, còn Structured Concurrency vẫn preview. Không coi hai API này có cùng trạng thái ổn định.

Nếu ứng dụng dùng ThreadLocal để truyền context, đừng chuyển toàn bộ sang Scoped Values chỉ vì API đã final. Đánh giá semantics của context, vòng đời, khả năng ghi và tích hợp với framework trước khi thay đổi.

### 7.7. GC, memory và performance

Hiệu năng có thể thay đổi dù code không thay đổi. Cần lưu baseline ở JDK 21 và so sánh với JDK 25 bằng cùng dữ liệu và cùng điều kiện.

Các chỉ số nên theo dõi:

- Startup time và thời gian đạt steady state.
- Throughput và latency p50/p95/p99.
- Heap occupancy, allocation rate và live set.
- GC pause, concurrent cycle và CPU overhead.
- Native memory, direct buffer và thread count.
- CPU utilization, context switching và lock contention.
- Tỷ lệ lỗi, timeout và retry trong luồng tích hợp.

Nếu dùng ZGC, hãy chú ý thay đổi generational mode từ 23 và việc loại bỏ non-generational mode ở 24. Nếu dùng G1 hoặc Shenandoah, hãy thử các thay đổi hiệu năng ở JDK 25 bằng benchmark đại diện. Không thay collector mặc định hoặc heap flags cùng lúc với việc đổi JDK trừ khi có lý do rõ ràng.

### 7.8. Bảo mật và mật mã

Rà soát các thành phần sau:

- Provider và thuật toán JCA/JCE được ứng dụng chỉ định.
- TLS handshake, trust store, certificate chain và proxy.
- Keystore format, key algorithm và key size.
- Native library hoặc provider bên ngoài JVM.
- Security Manager policy cũ.
- JNI/native access và quyền module.
- Secret, token và credential được truyền qua biến môi trường hoặc file.

JDK mới có thể bổ sung thuật toán nhưng không có nghĩa mọi hệ thống đối tác đã hỗ trợ chúng. Hãy kiểm tra khả năng tương tác ở cả hai đầu. Không thay đổi thuật toán mật mã production chỉ vì thuật toán mới xuất hiện trong provider của JDK.

## 8. Quy trình migration đề xuất

### Giai đoạn 1: Ghi nhận baseline trên JDK 21

Trước khi thay đổi, lưu lại trạng thái hiện tại:

1. Phiên bản vendor và build của JDK 21.
2. Maven/Gradle wrapper, compiler plugin và các plugin build.
3. Dependency tree và phiên bản framework.
4. JVM flags, GC, heap, module flags và native access flags.
5. Container base image hoặc hệ điều hành triển khai.
6. Unit test, integration test, startup time và các chỉ số hiệu năng.
7. Warning hiện có, đặc biệt về deprecation, reflection và native code.

Baseline cần đủ chi tiết để so sánh. Nếu chỉ ghi nhận rằng build thành công, sẽ khó xác định nguyên nhân khi runtime hoặc hiệu năng thay đổi.

### Giai đoạn 2: Kiểm kê rủi ro trong source và dependency

Tìm các điểm phụ thuộc đặc biệt:

- **System.setSecurityManager** và các class policy.
- **java.applet**.
- **sun.misc.Unsafe** và các package nội bộ.
- JNI, **System.load**, **System.loadLibrary** và FFM.
- **--enable-preview** và preview API.
- **--add-opens**, **--add-exports** và reflective access.
- Framework sửa final field.
- Virtual thread, **synchronized** và native blocking call.
- Tùy chọn ZGC generational/non-generational.
- Agent và thư viện thao tác bytecode.

Phân loại từng kết quả theo mức độ:

| Mức | Ý nghĩa | Ví dụ |
|---|---|---|
| Cao | Có thể khiến build hoặc startup thất bại, hoặc làm mất cơ chế bảo mật đang dùng | Applet API bị xóa, Security Manager bị vô hiệu hóa, JDK 32-bit không còn |
| Trung bình | Có thể gây warning, thay đổi hành vi hoặc lỗi trong một code path cụ thể | JNI native access, Unsafe, final-field reflection, ZGC flags |
| Thấp | Chủ yếu liên quan công cụ, cú pháp hoặc khả năng tối ưu mới | Markdown Javadoc, multi-file launch, JFR event mới |

Mức độ thực tế còn phụ thuộc việc ứng dụng có sử dụng thành phần đó hay không. Đừng đánh dấu một hạng mục là rủi ro cao chỉ vì JEP tồn tại; hãy tìm bằng chứng trong source, dependency tree, cấu hình và runtime log.

### Giai đoạn 3: Cập nhật build tool và dependency có ràng buộc

Trước khi chuyển production runtime, cập nhật các công cụ cần thiết để chúng có thể chạy trên JDK 25:

- Chọn phiên bản Maven/Gradle và plugin có hỗ trợ JDK 25.
- Cập nhật compiler, test engine và annotation processor.
- Cập nhật framework và agent có liên quan đến reflection, bytecode hoặc native access.
- Kiểm tra dependency native theo OS/architecture.
- Giữ dependency lock hoặc dependency management để build tái lập.

Có thể tạm giữ **--release 21** trong giai đoạn này nếu sản phẩm vẫn cần hỗ trợ runtime 21. Điều đó giúp tách lỗi do toolchain mới khỏi lỗi do source/API target mới.

### Giai đoạn 4: Thêm JDK 25 vào CI

Tạo một job CI dùng JDK 25 và chạy cùng bộ kiểm thử hiện tại. Nếu có thể, duy trì một job JDK 21 để xác nhận khả năng tương thích ngược trong giai đoạn chuyển tiếp.

Không nhất thiết phải triển khai production trên JDK 22, 23 và 24. Tuy nhiên, nếu một lỗi xuất hiện trên JDK 25 và chưa rõ nguyên nhân, có thể dùng các bản trung gian để khoanh vùng release đã thay đổi hành vi. Khi làm vậy, hãy ghi nhận rõ vendor/build của từng JDK và dùng cùng artifact hoặc cùng source commit.

### Giai đoạn 5: Xử lý warning trước khi chúng trở thành lỗi

Chạy ứng dụng và test trên JDK 25, thu thập warning về:

- Unsafe memory access.
- JNI/native access.
- Final-field mutation.
- Deprecated hoặc for-removal API.
- Preview feature và module access.
- GC flags không còn được hỗ trợ.

Với mỗi warning, ghi rõ caller, dependency sở hữu code, ảnh hưởng, bản nâng cấp hoặc cách thay thế và người phụ trách. Không tắt warning hàng loạt trước khi hiểu nguồn gốc.

### Giai đoạn 6: Kiểm thử tích hợp trong môi trường triển khai thật

Chạy trên đúng loại OS, architecture, container image và tài khoản service. Đặc biệt kiểm tra:

- Native library có được chọn đúng variant và nạp thành công.
- Module có đủ native access và package access cần thiết.
- Framework reflection/serialization/ORM hoạt động đúng.
- Virtual thread và blocking operation đạt throughput mong muốn.
- GC và memory usage đáp ứng SLO.
- TLS, database, messaging và file I/O hoạt động.
- Monitoring agent, profiler và JFR vẫn thu thập dữ liệu.
- Script startup, health check và shutdown hoạt động.

### Giai đoạn 7: Canary và rollout

Triển khai một phần workload trên JDK 25 trước. So sánh lỗi, latency, CPU, memory, GC, startup và tỷ lệ retry với baseline. Chỉ mở rộng khi các chỉ số nằm trong ngưỡng chấp nhận.

Giữ khả năng rollback bằng cách lưu artifact, image và cấu hình JDK 21 đã biết hoạt động. Nếu thay đổi bytecode target, dependency hoặc schema dữ liệu, hãy xác nhận rollback không bị chặn bởi thay đổi không tương thích.

## 9. Các lệnh và công cụ hỗ trợ kiểm tra

### 9.1. Xác nhận toolchain thực tế

Chạy trong đúng terminal hoặc container mà CI/production dùng:

```shell
java -version
javac -version
mvn -version
./gradlew --version
```

Không phải dự án nào cũng dùng cả Maven và Gradle. Mục tiêu là xác nhận runtime của build tool, compiler và JVM chạy ứng dụng. Một máy có thể cài nhiều JDK; **JAVA_HOME** và **PATH** không nhất thiết trỏ cùng một bản.

### 9.2. Tìm dependency dùng internal JDK API

Có thể dùng jdeps để phát hiện dependency vào JDK internals:

```shell
jdeps --jdk-internals application.jar
```

Nếu kết quả chỉ ra thư viện bên thứ ba, hãy xác định artifact và nâng cấp hoặc thay thế thư viện đó. Không tự động coi mọi package bắt đầu bằng **com.sun** là lỗi; đọc đúng kết quả và đối chiếu API có được hỗ trợ công khai hay không.

### 9.3. Kiểm tra API đã deprecated hoặc for removal

Có thể dùng jdeprscan để quét artifact theo release đích:

```shell
jdeprscan --release 25 --for-removal application.jar
```

Kết quả là tín hiệu điều tra, không thay thế compile và test. Một số dependency chỉ được nạp động hoặc gọi qua reflection nên không thể phát hiện đầy đủ bằng phân tích tĩnh.

### 9.4. Kiểm tra class-file version

Dùng javap để xem thông tin class file:

```shell
javap -verbose -classpath application.jar com.example.Main
```

Tìm dòng **major version** trong output. Đối chiếu với phiên bản runtime tối thiểu mà sản phẩm hỗ trợ. Nếu dùng multi-release JAR, cần kiểm tra cả các entry theo phiên bản Java.

### 9.5. Theo dõi GC và runtime

Có thể bật GC logging khi chạy thử:

```shell
java -Xlog:gc* -jar application.jar
```

Đối với profiling, dùng Java Flight Recorder trên một workload đại diện và phân tích bằng công cụ tương thích với JDK 25. Ghi lại đầy đủ JVM flags, heap size và container limit để so sánh có ý nghĩa.

Không nên bật log chi tiết trong production vô thời hạn nếu chưa đánh giá dung lượng và chi phí vận hành. Dùng cấu hình có kiểm soát, thu thập trong khoảng thời gian phù hợp và bảo vệ file log theo chính sách dữ liệu của tổ chức.

## 10. Các tình huống lỗi thường gặp khi chuyển lên JDK 25

### Tình huống 1: Build thất bại vì không tìm thấy Applet API

**Nguyên nhân có thể:** source hoặc dependency còn tham chiếu **java.applet**, API đã bị loại bỏ trong JDK 25.

**Cách xử lý:** xác định module sở hữu tham chiếu, kiểm tra có cần chức năng applet hay không, rồi thay thế kiến trúc hoặc nâng cấp dependency. Nếu dependency cũ không còn được duy trì, cần đánh giá khả năng loại bỏ hoặc thay bằng thư viện khác.

### Tình huống 2: Ứng dụng không thể bật Security Manager

**Nguyên nhân có thể:** script vẫn truyền tùy chọn bật Security Manager hoặc code gọi **System.setSecurityManager**.

**Cách xử lý:** bỏ giả định rằng JVM sẽ thực thi Security Manager. Chuyển giới hạn quyền sang OS/container/network policy và thiết kế lại nơi dựa vào permission check.

### Tình huống 3: Có warning khi tải native library

**Nguyên nhân có thể:** module chưa khai báo native access, thư viện dùng JNI hoặc runtime mới cảnh báo về hành vi native.

**Cách xử lý:** xác định module và caller, cập nhật dependency, cấp quyền native access đúng phạm vi. Sau đó kiểm tra OS, architecture và ABI của thư viện riêng biệt.

### Tình huống 4: Warning hoặc lỗi xuất hiện từ Unsafe

**Nguyên nhân có thể:** thư viện serializer, concurrency, memory mapping hoặc framework hiệu năng cao vẫn gọi memory-access method của **sun.misc.Unsafe**.

**Cách xử lý:** tìm stack trace và phiên bản dependency, cập nhật thư viện, kiểm tra lộ trình chuyển sang VarHandle hoặc FFM. Không chỉ loại bỏ warning khỏi log.

### Tình huống 5: GC hoạt động khác sau khi bật ZGC

**Nguyên nhân có thể:** JDK 23 chuyển generational mode thành mặc định và JDK 24 loại bỏ non-generational mode.

**Cách xử lý:** rà soát JVM flags, chạy benchmark có cùng workload, so sánh pause, throughput, CPU và memory. Điều chỉnh theo số liệu thay vì khôi phục một flag đã bị loại bỏ.

### Tình huống 6: Framework hoặc serializer cảnh báo khi ghi final field

**Nguyên nhân có thể:** framework dùng reflection sâu để thay đổi final field sau khi object đã được tạo.

**Cách xử lý:** cập nhật framework, dùng constructor hoặc API serialization được hỗ trợ và xác minh invariant của object. Xác định rõ dependency nào cần xử lý trước khi các hạn chế tương lai trở nên nghiêm ngặt hơn.

### Tình huống 7: Agent hoặc framework không xử lý được class file

**Nguyên nhân có thể:** agent, ASM, Byte Buddy hoặc công cụ tương tự chưa hỗ trợ class-file version hoặc runtime mới.

**Cách xử lý:** nâng cấp agent và thư viện bytecode, xác minh compatibility matrix của nhà cung cấp, chạy integration test với đúng tùy chọn startup. Tạm thời loại agent khỏi môi trường test có thể giúp khoanh vùng, nhưng không phải giải pháp production nếu agent là thành phần bắt buộc.

### Tình huống 8: Ứng dụng chạy được nhưng hiệu năng giảm

**Nguyên nhân có thể:** GC mode, JIT warm-up, heap/container sizing, dependency hoặc workload khác với baseline.

**Cách xử lý:** so sánh JFR, GC log, allocation, CPU, lock contention và latency. Thay đổi một nhóm cấu hình mỗi lần để xác định tác động.

## 11. Checklist hoàn tất migration JDK 21 lên 25

### Source code và API

- [ ] Đã tìm Security Manager và loại bỏ giả định dựa vào cơ chế này.
- [ ] Đã tìm tham chiếu **java.applet** và xử lý dependency liên quan.
- [ ] Đã kiểm kê **sun.misc.Unsafe** và các JDK internal API.
- [ ] Đã kiểm tra **--enable-preview** và các preview API đang dùng.
- [ ] Đã kiểm tra reflection sửa final field.
- [ ] Đã rà soát JNI, FFM và native access.

### Build và dependency

- [ ] Maven/Gradle wrapper và plugin hỗ trợ JDK 25.
- [ ] Annotation processor, test engine, mocking framework và compiler plugin tương thích.
- [ ] Bytecode library và Java agent hỗ trợ runtime đích.
- [ ] Framework, JDBC driver và thư viện tích hợp đã được kiểm tra.
- [ ] **--release** được đặt theo phiên bản runtime tối thiểu mà sản phẩm cam kết.
- [ ] Artifact được build tái lập và dependency được khóa theo quy trình của dự án.

### Runtime và triển khai

- [ ] JVM flags đã được rà soát theo JDK 25.
- [ ] ZGC flags cũ đã được kiểm tra; không còn yêu cầu non-generational mode.
- [ ] Native library đúng OS, architecture và ABI.
- [ ] Container base image và OS đáp ứng yêu cầu 64-bit.
- [ ] Script startup, shutdown, health check và service account hoạt động.
- [ ] TLS, trust store, database và messaging đã được kiểm tra.

### Kiểm thử và phát hành

- [ ] Unit test và integration test chạy thành công trên JDK 25.
- [ ] Test có reflection, serialization, proxy và instrumentation đã chạy.
- [ ] Native loading và native function call đã được kiểm tra.
- [ ] GC, memory, startup và throughput đã được so sánh với baseline JDK 21.
- [ ] Warning deprecation, Unsafe, JNI và final-field mutation đã có chủ sở hữu xử lý.
- [ ] Canary đạt ngưỡng SLO.
- [ ] Artifact, image và cấu hình rollback đã được lưu giữ.

## Kết luận

Nâng cấp JDK 21 lên JDK 25 cần rà soát cả bốn release trung gian vì nhiều thay đổi quan trọng xuất hiện trước mốc đích. JDK 22 hoàn thiện FFM; JDK 23 thay đổi mặc định ZGC và deprecate memory-access methods của Unsafe; JDK 24 vô hiệu hóa Security Manager, điều chỉnh virtual thread, hoàn thiện Class-File API và Stream Gatherers, đồng thời chuẩn bị siết JNI; JDK 25 hoàn thiện một số API preview, loại bỏ Applet API và tiếp tục hạn chế các nền tảng 32-bit.

Hãy bắt đầu từ baseline JDK 21, kiểm kê source và dependency, cập nhật toolchain, chạy CI trên JDK 25, xử lý warning và kiểm thử trong đúng môi trường triển khai. Chỉ sau khi hành vi, hiệu năng và vận hành được xác nhận mới rollout rộng. Cách làm này giúp xác định chính xác thay đổi nào ảnh hưởng đến ứng dụng và giữ cho migration có thể kiểm chứng, lặp lại và rollback khi cần.

