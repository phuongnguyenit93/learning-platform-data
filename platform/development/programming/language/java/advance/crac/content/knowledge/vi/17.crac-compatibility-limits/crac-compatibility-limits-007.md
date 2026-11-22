# Tương thích theo checkpoint engine và phần mở rộng của nhà cung cấp

CRaC cho phép ứng dụng Java chuẩn bị tài nguyên trước checkpoint và phục hồi chúng sau restore. Tuy nhiên, khả năng tạo và khôi phục checkpoint còn phụ thuộc vào thành phần thực hiện việc chụp và phục hồi trạng thái tiến trình. Thành phần này thường được gọi là checkpoint engine hoặc checkpoint/restore implementation. Nó làm việc ở tầng runtime và hệ điều hành, trong khi CRaC API cung cấp hợp đồng để ứng dụng phối hợp vòng đời tài nguyên.

Hai ứng dụng cùng triển khai org.crac.Resource chưa chắc có thể dùng chung một checkpoint. Chúng có thể chạy trên JDK vendor khác nhau, engine khác nhau, kernel khác nhau hoặc dựa vào phần mở rộng riêng của nhà cung cấp. Một checkpoint thường gắn chặt với tổ hợp runtime và môi trường đã tạo ra nó. Vì vậy, khi phát hành, cần xác định rõ engine nào tạo checkpoint, phiên bản nào được hỗ trợ, extension nào tham gia và điều kiện nào phải được giữ tương thích ở môi trường restore.

## 1. Phân biệt CRaC API, JDK runtime và checkpoint engine

Một quy trình CRaC có nhiều lớp phối hợp:

~~~text
Ứng dụng Java
    |
    |  Resource: beforeCheckpoint / afterRestore
    v
CRaC API và integration của framework/thư viện
    |
    v
JDK runtime / JVM build có hỗ trợ CRaC
    |
    |  Điều phối checkpoint, thread và trạng thái JVM
    v
Checkpoint engine / native implementation
    |
    |  Chụp và phục hồi trạng thái process, memory,
    |  file descriptor và tài nguyên hệ điều hành được hỗ trợ
    v
Kernel, CPU, filesystem, container và host
~~~

Các lớp này có trách nhiệm khác nhau:

- **CRaC API:** cung cấp hợp đồng để ứng dụng đăng ký Resource và thực hiện callback trước checkpoint, sau restore.
- **JDK runtime:** tích hợp CRaC vào JVM, điều phối trạng thái Java, runtime và các hook cần thiết.
- **Checkpoint engine:** thực hiện phần việc native để lưu và khôi phục trạng thái tiến trình theo khả năng của nền tảng.
- **Vendor extension:** phần mở rộng do nhà cung cấp JDK hoặc nền tảng cung cấp để bổ sung tích hợp, hook, Resource adapter, công cụ hoặc tính năng riêng.
- **Môi trường triển khai:** kernel, CPU, container runtime, filesystem, namespace, quyền và các dependency bên ngoài mà checkpoint cần.

Ví dụ, ứng dụng có thể dùng Core.getGlobalContext().register(resource) để đăng ký một Resource theo CRaC API. Lời gọi này không chỉ định engine native cụ thể và cũng không chứng minh checkpoint được tạo bằng một engine có thể restore trên mọi host.

Checkpoint engine thường được tích hợp vào hoặc được gọi bởi một JDK/runtime cụ thể. Một số nền tảng sử dụng CRIU trên Linux; một số bản phân phối có thể cung cấp cách tích hợp, công cụ hoặc extension riêng. Không nên suy luận engine đang dùng chỉ từ tên API Java. Hãy lấy thông tin từ tài liệu của đúng JDK distribution, lệnh tạo checkpoint và log runtime thực tế.

## 2. Checkpoint engine quyết định điều gì?

Checkpoint engine làm việc với trạng thái tiến trình ở tầng thấp hơn object Java. Tùy implementation, nó có thể cần lưu hoặc tái lập:

- Các vùng nhớ của tiến trình và trạng thái CPU cần thiết để tiếp tục thực thi.
- Cây tiến trình và quan hệ giữa các process/thread được hỗ trợ.
- File descriptor, pipe, socket và các tài nguyên kernel được engine hỗ trợ.
- Namespace, cgroup, mount và thông tin môi trường liên quan.
- Trạng thái cần thiết để tái lập tiến trình trong container hoặc host.
- Thông tin phối hợp với các tài nguyên bên ngoài hoặc tài nguyên cần xử lý riêng.

Phạm vi hỗ trợ không giống nhau giữa mọi engine và phiên bản. Một engine có thể hỗ trợ một loại socket hoặc namespace trong một cấu hình nhưng không hỗ trợ trong cấu hình khác. Có tài nguyên cần được đóng trước checkpoint, có tài nguyên được engine hỗ trợ, có tài nguyên phải được mở lại sau restore và có tài nguyên không thể phục hồi bằng checkpoint.

Checkpoint engine không hiểu đầy đủ ý nghĩa nghiệp vụ của object Java. Nó có thể nhìn thấy file descriptor hoặc bộ nhớ, nhưng không biết một transaction đã commit chưa, message đã được xác nhận chưa hay một lease phân tán còn thuộc về ứng dụng không. Đó là lý do CRaC Resource và logic nghiệp vụ vẫn cần phối hợp.

### Engine không thay thế Resource

Giả sử một ứng dụng giữ một object JDBC Connection. Engine có thể xử lý một số trạng thái native của process, nhưng điều đó không chứng minh session database ở server vẫn còn hợp lệ khi restore. Database là hệ thống độc lập và tiếp tục vận hành theo thời gian của nó.

Tương tự, engine có thể phục hồi trạng thái file descriptor trong phạm vi được hỗ trợ, nhưng ứng dụng vẫn phải xác định file có bị thay đổi, quyền truy cập có còn đúng và vị trí logic đã xử lý là gì.

Vì vậy:

- Dùng CRaC Resource để chuẩn bị và phục hồi những tài nguyên mà ứng dụng sở hữu.
- Dùng khả năng của engine cho những tài nguyên được implementation xác nhận hỗ trợ.
- Dùng API của dịch vụ bên ngoài để xác minh hoặc tái tạo trạng thái từ xa.
- Không dựa vào việc engine khôi phục process để suy ra hệ thống bên ngoài đã quay về thời điểm checkpoint.

## 3. Không phải checkpoint nào cũng có định dạng tương thích chéo

Checkpoint chứa trạng thái runtime và process, không phải một file dữ liệu Java độc lập có thể mở trên bất kỳ JVM nào. Artifact có thể phụ thuộc vào:

- JDK vendor, phiên bản và build number.
- CRaC runtime/API integration.
- Phiên bản và cấu hình checkpoint engine.
- Phiên bản kernel và tính năng kernel được sử dụng.
- Kiến trúc CPU và các instruction set mà mã máy/runtime yêu cầu.
- Native library, libc và ABI.
- Container image, filesystem, mount point và namespace.
- JVM flags, module path, native agent và cấu hình lúc tạo checkpoint.

Do đó, việc cùng có Java 21 hoặc cùng chạy Linux không đủ để chứng minh tương thích. Hai image được tạo trên hai JDK vendor khác nhau có thể có khác biệt trong JVM build, native integration, checkpoint engine và extension. Ngay cả khi cùng vendor, hai build hoặc engine version khác nhau vẫn có thể có yêu cầu tương thích khác nhau.

Hãy xem checkpoint như một artifact gắn với một compatibility profile đã được kiểm chứng. Profile đó phải nêu rõ producer (môi trường tạo ảnh) và consumer (môi trường restore) được phép sử dụng artifact.

## 4. Những trục tương thích cần kiểm tra

| Trục | Thông tin cần ghi | Vì sao quan trọng |
|---|---|---|
| JDK vendor và build | Vendor, runtime version đầy đủ, build number | JVM và native integration có thể khác nhau |
| CRaC API/runtime | Phiên bản API, implementation và integration | Callback, runtime behavior hoặc extension có thể thay đổi |
| Checkpoint engine | Tên engine, phiên bản, build và tùy chọn | Định dạng và khả năng phục hồi phụ thuộc implementation |
| OS và kernel | Distribution, kernel release và cấu hình cần thiết | Engine phụ thuộc tính năng kernel |
| CPU | Architecture, ABI và feature được yêu cầu | Mã máy và trạng thái CPU có thể không chuyển được giữa các nền tảng |
| Native dependencies | libc, shared libraries, JNI và native agents | Process có thể phụ thuộc ABI và thư viện trên host |
| Container | Base image digest, runtime, namespace và cgroup | Restore phải nhìn thấy môi trường filesystem và process phù hợp |
| Filesystem | Mount, path, permission và loại filesystem | File handle và đường dẫn có thể không tồn tại hoặc khác trạng thái |
| JVM options | Flags, agents, module options và system properties liên quan | Các option có thể ảnh hưởng layout hoặc hành vi runtime |
| Vendor extensions | Tên, phiên bản và cấu hình extension | Extension có thể bổ sung hook hoặc định dạng riêng |
| External resources | Database, broker, secret store, lock và endpoint | Các dịch vụ này không tự quay lại trạng thái checkpoint |

Không phải mọi dự án đều cần ghi mọi trường ở cùng mức chi tiết. Hãy bắt đầu từ yêu cầu của engine và vendor, sau đó ghi những yếu tố có thể ảnh hưởng đến restore. Không ghi một giá trị giả để lấp trường còn thiếu; dùng unknown hoặc đánh dấu chưa xác minh.

## 5. Phân biệt tương thích API và tương thích checkpoint

Đây là hai khái niệm thường bị nhầm lẫn:

**Tương thích API** nói về khả năng biên dịch và chạy mã nguồn với API mà ứng dụng sử dụng. Ví dụ, một class triển khai org.crac.Resource có thể biên dịch trên một JDK cung cấp CRaC API tương ứng.

**Tương thích checkpoint** nói về khả năng một runtime và engine cụ thể khôi phục đúng artifact checkpoint đã tạo. Nó liên quan đến native state, kernel, CPU, engine version, container và các extension.

Một ứng dụng có thể:

- Biên dịch thành công trên JDK A.
- Chạy thành công và tạo checkpoint bằng JDK A cùng engine X.
- Vẫn không thể restore checkpoint đó bằng JDK B hoặc engine Y.

Điều này không nhất thiết là lỗi source code hoặc vi phạm Java API. Đó có thể là giới hạn tương thích của checkpoint artifact.

Tương tự, việc hai JDK cùng cung cấp interface org.crac.Resource không chứng minh callback được điều phối giống hệt nhau trong mọi tình huống hoặc checkpoint image của chúng có thể dùng chéo.

## 6. Phần mở rộng của nhà cung cấp có thể bao gồm những gì?

Vendor extension là các cơ chế bổ sung ngoài hợp đồng CRaC API chung. Tùy nhà cung cấp, extension có thể bao gồm:

- Resource adapter cho framework hoặc thư viện cụ thể.
- Hook trước/sau checkpoint ở cấp runtime hoặc launcher.
- Cơ chế đăng ký Resource tự động.
- Tích hợp với connection pool, TLS, native library hoặc client SDK.
- Lệnh, option hoặc cấu hình riêng để gọi checkpoint/restore.
- Kiểm tra điều kiện môi trường trước khi checkpoint.
- Công cụ diagnostics để báo tài nguyên chưa sẵn sàng hoặc lỗi restore.
- Native integration hoặc engine patch riêng.

Danh sách này mô tả các loại khả năng có thể gặp, không phải một API chung mà mọi vendor đều phải cung cấp. Tên class, package, option dòng lệnh, hành vi callback và mức hỗ trợ phải được xác minh từ tài liệu chính thức của đúng vendor và đúng phiên bản.

### Extension không tự động là chuẩn portable

Một ứng dụng có thể dùng CRaC API chuẩn và một extension riêng của vendor. Phần dùng API chuẩn có thể dễ chuyển đổi hơn về mặt source, nhưng extension có thể ràng buộc ứng dụng với:

- Một JDK distribution cụ thể.
- Một phiên bản extension.
- Một checkpoint engine hoặc một engine build.
- Một framework integration cụ thể.
- Một bộ JVM flags hoặc launcher options.

Nếu source gọi trực tiếp class riêng của vendor, chuyển sang JDK khác có thể cần thay đổi code hoặc module dependency. Nếu extension chỉ được cấu hình ở runtime, source có thể biên dịch trên nhiều JDK nhưng checkpoint artifact vẫn có thể không tương thích giữa các engine.

## 7. Cách cô lập phần mở rộng riêng của vendor

Khi cần dùng extension riêng, nên cô lập nó sau một abstraction do ứng dụng kiểm soát. Phần nghiệp vụ không nên phụ thuộc trực tiếp vào tên class hoặc callback độc quyền nếu không cần.

Ví dụ, ứng dụng định nghĩa một interface trung lập:

~~~java
public interface CheckpointIntegration {
    void prepare() throws Exception;

    void restored() throws Exception;

    default void checkpointAborted() throws Exception {
        // Mặc định không làm gì; implementation có thể phục hồi riêng.
    }
}
~~~

Implementation dùng CRaC API chuẩn có thể đăng ký một Resource adapter:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CracResourceAdapter implements Resource {
    private final CheckpointIntegration integration;

    public CracResourceAdapter(CheckpointIntegration integration) {
        this.integration = integration;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        integration.prepare();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        integration.restored();
    }
}
~~~

Ứng dụng có thể có một implementation trung lập và các implementation riêng cho từng runtime khi thực sự cần. Chỉ tạo implementation vendor-specific sau khi xác định được extension API chính thức. Không tự đặt tên class, method hoặc JVM flag theo phỏng đoán.

Một cấu trúc module có thể là:

~~~text
application/
  domain/
    CheckpointIntegration.java
  runtime-crac/
    CracResourceAdapter.java
  runtime-vendor-a/
    VendorACheckpointIntegration.java
  runtime-vendor-b/
    VendorBCheckpointIntegration.java
~~~

Module domain không phụ thuộc JDK vendor. Module runtime-crac dùng CRaC API chuẩn. Module vendor-specific chỉ được đưa vào build khi deployment profile chọn đúng runtime. Nếu ứng dụng chỉ triển khai trên một vendor, không cần tạo nhiều adapter giả định; giữ integration nhỏ và pin dependency rõ ràng.

### Không bọc extension để che giấu khác biệt ngữ nghĩa

Một abstraction chỉ hữu ích nếu các implementation có thể thực hiện cùng một hợp đồng. Nếu vendor A hỗ trợ phục hồi một loại socket còn vendor B không hỗ trợ, không nên tạo method chung tên restoreAllSockets() rồi giả vờ hai implementation tương đương.

Hãy biểu diễn capability rõ ràng, ví dụ:

~~~java
public record CheckpointCapabilities(
        boolean supportsUnixSockets,
        boolean supportsTcpConnections,
        boolean supportsFileLocks,
        boolean supportsNativeMappings) {}
~~~

Các giá trị capability phải được cung cấp từ cấu hình đã xác minh hoặc thông tin runtime chính thức. Không tự suy ra từ vendor name hay major version. Ứng dụng có thể dùng capability profile để từ chối một cấu hình không đáp ứng yêu cầu trước khi tạo checkpoint.

## 8. Tương thích theo checkpoint engine: ví dụ với engine và native state

CRIU là một checkpoint/restore engine thường gặp trong môi trường Linux. Nó làm việc ở tầng process và kernel, còn CRaC runtime phối hợp với JVM và ứng dụng để chuẩn bị trạng thái Java. Cách tích hợp, phiên bản CRIU, tùy chọn và tính năng được hỗ trợ phụ thuộc vào JDK distribution và môi trường triển khai.

Khi một CRaC runtime dùng CRIU hoặc một engine tương tự, cần xác minh:

- Engine version được JDK distribution hỗ trợ.
- Kernel có các tính năng cần thiết và được cấu hình phù hợp.
- Quyền và capability của process có đủ cho thao tác checkpoint/restore.
- Container runtime cho phép các thao tác namespace/cgroup cần thiết.
- Filesystem và mount cần thiết còn hiện diện ở môi trường restore.
- Network resource được xử lý theo cách mà engine hỗ trợ.
- Các file descriptor hoặc native handle đặc biệt đã được đóng, tái tạo hoặc xử lý theo tài liệu.

Không nên cài một phiên bản engine mới hơn vào host rồi giả định JDK cũ sẽ tương thích. JDK distribution có thể được build và kiểm thử với một dải phiên bản engine cụ thể. Hãy dùng tổ hợp được vendor xác nhận.

### Ví dụ một compatibility profile

Một profile phát hành nội bộ có thể ghi:

~~~yaml
checkpointProfile:
  id: "linux-x86_64-crac-profile-01"
  java:
    vendor: "recorded-vendor"
    runtimeVersion: "recorded-full-version"
    cracApiVersion: "recorded-version"
  engine:
    name: "criu"
    version: "recorded-version"
    optionsProfile: "production-default"
  host:
    os: "recorded-distribution"
    kernel: "recorded-kernel"
    architecture: "x86_64"
    libc: "recorded-libc"
  container:
    imageDigest: "sha256:..."
    runtime: "recorded-container-runtime"
  extensions:
    - name: "vendor-resource-integration"
      version: "recorded-version"
  restorePolicy:
    allowedProfile: "linux-x86_64-crac-profile-01"
    coldStartFallback: true
~~~

Các giá trị recorded-* và digest ở trên là placeholder minh họa. Pipeline cần thay bằng thông tin thực tế đã thu thập từ môi trường tạo checkpoint. Không nên sao chép profile này thành cấu hình triển khai mà chưa xác minh yêu cầu của engine và vendor.

## 9. Kiểm soát phiên bản extension và dependency

Vendor extension có thể được đóng gói theo nhiều cách:

- Dependency Maven/Gradle nằm trong application artifact.
- Module hoặc agent được thêm vào JVM.
- Native library được cài trong container/base image.
- Script hoặc binary được gọi bởi checkpoint launcher.
- Cấu hình runtime nằm ngoài JAR.

Mỗi cách đóng gói có vòng đời version riêng. Chỉ ghi phiên bản JAR ứng dụng là chưa đủ.

Nên ghi:

- Tên và version của extension.
- Artifact coordinates hoặc package identifier.
- Hash của JAR, agent hoặc binary.
- Native library version và hash nếu cần.
- JVM flags hoặc launcher options liên quan.
- Phiên bản framework integration.
- Dải JDK và engine được extension hỗ trợ theo tài liệu vendor.

Nếu extension có dependency bắc cầu, hãy đưa chúng vào lockfile/SBOM. Tránh dùng version range không được kiểm soát cho thành phần ảnh hưởng tới checkpoint. Build và checkpoint nên pin phiên bản cụ thể để cùng một release có thể truy vết.

## 10. Thứ tự callback và giới hạn của extension

Không phải mọi vendor extension đều có cùng thứ tự chạy hoặc cùng ngữ nghĩa với CRaC Resource. Một extension có thể:

- Tự đăng ký Resource vào context.
- Cung cấp callback bổ sung ở launcher.
- Chạy kiểm tra trước khi runtime gọi Resource.
- Quản lý native resource riêng.
- Thực hiện một bước xác minh sau restore.

Trước khi kết hợp extension với Resource do ứng dụng tự đăng ký, cần biết:

1. Extension có tự đăng ký Resource hay không.
2. Resource nào sở hữu cùng một client hoặc pool.
3. Thứ tự close và reopen có được bảo đảm không.
4. Callback có thể chạy nhiều lần hoặc thất bại giữa chừng không.
5. Nếu checkpoint bị hủy sau khi tài nguyên đã đóng, tiến trình ban đầu được phục hồi thế nào.
6. Extension có hỗ trợ đúng phiên bản framework và driver đang dùng không.

Tránh đăng ký hai Resource cùng đóng một connection pool. Tránh tự gọi callback của extension như thể đó là API chuẩn. Dùng đúng entry point được tài liệu công bố.

Nếu thứ tự phụ thuộc là bắt buộc, hãy gom các bước có quan hệ vào một coordinator có chủ sở hữu rõ ràng hoặc dùng lifecycle orchestration do framework/vendor hỗ trợ. Không dựa vào thứ tự tình cờ giữa các callback độc lập.

## 11. Xây dựng ma trận tương thích producer và consumer

Producer là môi trường tạo checkpoint; consumer là môi trường restore checkpoint. Ma trận cần xác định các tổ hợp được kiểm thử, không chỉ liệt kê các phiên bản đã cài.

Ví dụ cấu trúc ma trận:

| Producer | Consumer | Trạng thái | Ghi chú |
|---|---|---|---|
| JDK vendor A + engine X vN + Linux profile P | Cùng tổ hợp đã pin | Đã kiểm thử | Tổ hợp chuẩn của release |
| JDK vendor A build mới hơn + engine X vN+1 | Tổ hợp cũ | Chưa xác minh | Cần kiểm thử theo tài liệu vendor |
| JDK vendor B + engine Y | JDK vendor A + engine X | Không mặc định tương thích | Khác runtime/engine, cần hỗ trợ chính thức và thử nghiệm riêng |
| Linux x86_64 | Linux ARM64 | Không mặc định tương thích | Khác kiến trúc và trạng thái mã máy |
| Cùng JDK nhưng kernel khác | Host kernel khác | Chưa xác minh | Cần đối chiếu yêu cầu engine/kernel |
| Cùng app version nhưng native extension khác | Extension build khác | Chưa xác minh | Hash/version extension phải được kiểm soát |

Các trạng thái nên có ý nghĩa rõ ràng:

- **Supported:** vendor hoặc nền tảng xác nhận tổ hợp được hỗ trợ.
- **Tested:** tổ hợp đã chạy thành công trong kiểm thử nội bộ.
- **Not tested:** chưa có bằng chứng; không được suy ra là tương thích.
- **Unsupported:** vendor hoặc chính sách triển khai không hỗ trợ tổ hợp đó.

Một lần restore thành công trong môi trường thử nghiệm không nhất thiết tạo ra cam kết hỗ trợ chính thức. Ngược lại, tài liệu vendor nói một tổ hợp được hỗ trợ cũng không thay thế việc kiểm thử ứng dụng với tài nguyên và extension thực tế.

## 12. Quy trình xác minh trước khi phát hành checkpoint

Một quy trình thực tế có thể chia thành các giai đoạn:

### Xác định tổ hợp tạo checkpoint

1. Pin JDK vendor và phiên bản đầy đủ.
2. Xác định CRaC API/runtime build.
3. Xác định checkpoint engine, version và option profile.
4. Pin container base image bằng digest.
5. Ghi OS, kernel, CPU architecture, libc và native dependencies.
6. Liệt kê vendor extension, framework integration và hash artifact.
7. Ghi JVM flags và launcher configuration liên quan.

### Kiểm thử trên producer

1. Chạy ứng dụng trên đúng JDK và engine mục tiêu.
2. Xác nhận Resource và extension được đăng ký đúng.
3. Chạy các pre-check để phát hiện tài nguyên không được hỗ trợ.
4. Dừng request, consumer và transaction theo chính sách.
5. Tạo checkpoint bằng cơ chế được vendor hỗ trợ.
6. Ghi log và metadata thực tế của lần checkpoint.

### Kiểm thử trên consumer

1. Tạo môi trường restore theo compatibility profile.
2. Xác minh engine, runtime, kernel, CPU và container digest.
3. Kiểm tra checkpoint files và manifest.
4. Restore checkpoint bằng đúng quy trình triển khai.
5. Xác nhận callback và vendor extension hoàn tất.
6. Xác minh database, broker, secret, file và các dependency bên ngoài.
7. Chỉ mở readiness sau khi các dependency bắt buộc đã sẵn sàng.

### Kiểm thử thay đổi phiên bản

Khi nâng JDK, engine, kernel, base image hoặc extension, tạo checkpoint mới và chạy lại bộ kiểm thử. Không thay riêng một thành phần trong production rồi dùng checkpoint cũ nếu tổ hợp mới chưa được hỗ trợ hoặc chưa xác minh.

## 13. Gắn compatibility profile vào release manifest

Manifest checkpoint nên ghi các thành phần có ảnh hưởng đến restore. Ví dụ:

~~~json
{
  "application": {
    "version": "2.4.1",
    "commit": "full-commit-sha",
    "artifactSha256": "..."
  },
  "checkpoint": {
    "id": "release-checkpoint-001",
    "engine": {
      "name": "recorded-engine",
      "version": "recorded-version",
      "optionsProfile": "recorded-profile"
    }
  },
  "runtime": {
    "jdkVendor": "recorded-vendor",
    "javaVersion": "recorded-full-version",
    "cracRuntime": "recorded-version"
  },
  "platform": {
    "os": "recorded-os",
    "kernel": "recorded-kernel",
    "architecture": "x86_64",
    "libc": "recorded-libc",
    "containerDigest": "sha256:..."
  },
  "extensions": [
    {
      "name": "recorded-extension",
      "version": "recorded-version",
      "sha256": "..."
    }
  ],
  "compatibility": {
    "profileId": "linux-x86_64-crac-profile-01",
    "verification": "tested"
  }
}
~~~

Đây là ví dụ schema, không phải manifest chuẩn do CRaC quy định. Nên liên kết manifest này với checksum và chữ ký của release bundle. Giá trị version, hash và trạng thái verification phải đến từ pipeline kiểm chứng. Không đưa secret, token hoặc dữ liệu nhạy cảm vào metadata.

Khi restore, deployment controller hoặc script có thể đọc manifest để so sánh với runtime/host thực tế trước khi gọi engine. Nếu profile không khớp, dừng restore và chuyển sang cold start hoặc một artifact đã được xác minh tương thích.

## 14. Khi nào nên dùng extension của vendor?

Extension riêng có thể hữu ích khi nó giải quyết một phần tích hợp mà ứng dụng không nên tự quản lý, chẳng hạn:

- Hỗ trợ CRaC cho một connection pool hoặc SDK cụ thể.
- Tự động đăng ký Resource và quản lý thứ tự lifecycle.
- Xử lý một native handle đặc thù.
- Cung cấp diagnostics về tài nguyên không thể checkpoint.
- Tích hợp với engine hoặc launcher của JDK distribution.

Trước khi thêm extension, hãy xác nhận:

- Extension có được vendor duy trì và hỗ trợ không.
- Nó hỗ trợ đúng JDK build và engine version nào.
- Có tương thích với framework, driver và dependency version của ứng dụng không.
- Có tự đăng ký Resource hay yêu cầu đăng ký thủ công không.
- Có thay đổi command line, JVM flags, native library hoặc base image không.
- Cách nâng cấp và rollback extension.
- Cách xử lý khi extension không thể phục hồi tài nguyên.

Nếu extension chỉ hỗ trợ một dải runtime hẹp, hãy thể hiện ràng buộc đó trong compatibility profile. Không nên thêm extension chỉ vì tên sản phẩm có chữ CRaC; phải xác định nó thực sự hỗ trợ resource nào và giới hạn nào.

## 15. Chiến lược nâng cấp và rollback

Nâng một thành phần trong stack có thể ảnh hưởng đến khả năng restore. Cần quản lý version như một bộ:

~~~text
Release N
  Application build A
  JDK build J1
  CRaC integration C1
  Engine E1
  Extension X1
  Container digest I1
  Checkpoint artifact P1

Release N+1
  Application build B
  JDK build J2
  CRaC integration C2
  Engine E2
  Extension X2
  Container digest I2
  Checkpoint artifact P2
~~~

Nếu chỉ nâng JDK hoặc engine mà vẫn dùng checkpoint P1, cần có xác nhận tương thích từ vendor và kiểm thử cụ thể. Nếu không có, hãy tạo P2 trên tổ hợp mới.

Rollback cũng cần xét checkpoint. Có thể rollback application image nhưng checkpoint được tạo từ JDK/engine mới vẫn không dùng được với runtime cũ. Hãy giữ release bundle hoàn chỉnh của phiên bản trước, gồm application artifact, container digest, checkpoint artifact, manifest, extension và compatibility profile.

Một cold-start path được kiểm thử là phương án dự phòng quan trọng. Nếu checkpoint không tương thích hoặc restore thất bại, hệ thống có thể khởi động ứng dụng từ application artifact trên runtime được hỗ trợ, thay vì cố sử dụng checkpoint không phù hợp.

## 16. Các lỗi thường gặp

**Cho rằng CRaC API giống nhau nghĩa là checkpoint dùng chéo được.**

API tương thích ở tầng source không chứng minh định dạng checkpoint, JVM state hoặc native engine tương thích. Cần kiểm tra producer/consumer profile.

**Không ghi phiên bản checkpoint engine.**

Khi restore lỗi, không đủ thông tin để đối chiếu native implementation. Ghi engine name, version, options và nguồn cung cấp.

**Chỉ kiểm tra JDK major version.**

Vendor, build, CRaC patch, native integration và JVM flags có thể khác. Ghi runtime version đầy đủ.

**Tự nâng engine độc lập với JDK.**

JDK distribution có thể chỉ hỗ trợ một dải engine nhất định. Dùng tổ hợp được xác nhận và kiểm thử.

**Dùng vendor extension mà không pin version.**

Extension có thể thay đổi hook, resource support hoặc dependency. Ghi version và hash artifact.

**Đăng ký Resource trùng với extension.**

Hai thành phần cùng đóng một pool hoặc client có thể gây lỗi. Xác định rõ owner và trách nhiệm lifecycle.

**Giả định engine khôi phục database hoặc broker.**

Các dịch vụ bên ngoài tiếp tục vòng đời riêng. Phải reconnect, xác minh session và xử lý transaction/message theo chính sách.

**Dựa vào tên OS/container tag để kết luận tương thích.**

Tag có thể thay đổi; kernel, digest, CPU, libc và native library cũng quan trọng. Pin và ghi metadata cụ thể.

**Chỉ kiểm thử tạo checkpoint, không kiểm thử restore.**

Checkpoint thành công không chứng minh artifact có thể restore trên host đích. Cần integration test producer/consumer.

## 17. Kết luận

Khả năng tương thích của checkpoint phụ thuộc vào cả CRaC API, JDK runtime, checkpoint engine, vendor extension và môi trường hệ điều hành. CRaC Resource giúp ứng dụng phối hợp vòng đời tài nguyên, còn engine thực hiện phần checkpoint/restore native. Hai phần này bổ sung cho nhau nhưng không thay thế nhau.

Hãy pin và ghi nhận đầy đủ JDK vendor/build, CRaC runtime, engine/version/options, extension, kernel, CPU, native libraries và container digest. Xây dựng compatibility profile cho producer và consumer, dùng extension theo đúng tài liệu của nhà cung cấp, kiểm thử restore trên môi trường đích và giữ cold-start path để xử lý khi checkpoint không tương thích.
