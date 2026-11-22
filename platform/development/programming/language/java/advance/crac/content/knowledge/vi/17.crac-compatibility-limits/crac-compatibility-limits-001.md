# Tương thích giữa checkpoint và restore theo phiên bản, nhà cung cấp JDK

Checkpoint image của CRaC là trạng thái của một tiến trình Java đã chạy, bao gồm trạng thái JVM và những tài nguyên hệ điều hành mà cơ chế checkpoint hỗ trợ. Vì vậy, image phụ thuộc vào runtime đã tạo ra nó. Một image được tạo bằng một bản JDK CRaC cụ thể không mặc nhiên restore được bằng bất kỳ JDK nào khác, kể cả khi hai JDK có cùng số phiên bản Java.

Khi thiết kế quy trình phát hành, cần xác định rõ cặp môi trường **checkpoint runtime** và **restore runtime** được nhà cung cấp hỗ trợ. Những thông tin như vendor, distribution, phiên bản đầy đủ, build number, kiến trúc CPU, hệ điều hành, kernel, CRIU và thư viện native đều có thể ảnh hưởng đến khả năng tương thích. Cách an toàn là tạo một ma trận tương thích có bằng chứng kiểm thử, lưu thông tin runtime cùng image và chỉ triển khai các cặp checkpoint–restore đã được xác nhận.

## 1. Vì sao checkpoint image phụ thuộc JDK?

JVM không chỉ chạy bytecode. Trong lúc ứng dụng hoạt động, runtime tạo nhiều cấu trúc nội bộ như heap object, class metadata, thread stack, runtime data, code cache, cấu trúc quản lý bộ nhớ và trạng thái native. Checkpoint image có thể lưu một phần hoặc toàn bộ trạng thái tiến trình trong phạm vi mà bản CRaC và nền tảng hỗ trợ.

Những cấu trúc này phụ thuộc cách một bản JVM được xây dựng và triển khai. Hai bản JDK có cùng Java language level có thể khác nhau về:

- Cách bố trí và biểu diễn cấu trúc nội bộ của HotSpot hoặc JVM implementation khác.
- Cách quản lý heap, garbage collector, thread, monitor và code cache.
- Các bản vá bảo mật, native library và thành phần runtime được đóng gói.
- Cơ chế tích hợp CRaC, định dạng metadata và quy trình restore.
- Các cờ JVM, agent, module và thư viện đi kèm.

Vì vậy, việc ứng dụng biên dịch bằng Java 21 không chứng minh image được tạo bằng một JDK 21 có thể restore bằng mọi JDK 21 khác. Major version chỉ là một phần của danh tính runtime.

### 1.1. Phân biệt ba loại phiên bản

Khi ghi nhận môi trường, cần phân biệt:

| Khái niệm | Ví dụ minh họa | Ý nghĩa |
|---|---|---|
| Java feature version | 17, 21, 25 | Dòng phiên bản nền tảng Java |
| Update/patch version | 21.0.x | Bản cập nhật trong cùng feature release |
| Vendor build/distribution | Tên nhà cung cấp, build number, revision | Bản JDK cụ thể với các bản vá và tích hợp riêng |

Hai runtime có cùng feature version nhưng khác update hoặc build vẫn có thể không tương thích với cùng một checkpoint image. Ngược lại, một nhà cung cấp có thể công bố rõ một tập bản build tương thích hoặc hỗ trợ restore qua một số bản cập nhật. Chỉ được dựa vào phạm vi đó khi tài liệu của đúng nhà cung cấp và đúng dòng CRaC xác nhận.

### 1.2. Checkpoint image không phải bytecode portable

JAR và bytecode Java được thiết kế để chạy trên các JVM tương thích. Checkpoint image lại chứa trạng thái của một tiến trình cụ thể đã chạy. Có thể hình dung:

- JAR là đầu vào để JVM tạo một tiến trình mới.
- Checkpoint image là snapshot của tiến trình sau khi JVM đã nạp và khởi tạo ứng dụng.
- Restore khôi phục tiến trình từ snapshot theo quy tắc của runtime và hệ điều hành.

Do đó, không thể dùng quy tắc tương thích bytecode để suy ra quy tắc tương thích checkpoint image. Một JAR có thể chạy trên nhiều JDK trong khi image được tạo từ JAR đó vẫn chỉ restore được trên một tập runtime được hỗ trợ hẹp hơn.

## 2. Vai trò của nhà cung cấp JDK

CRaC cần sự phối hợp giữa JVM và nền tảng checkpoint/restore. Các nhà cung cấp JDK có thể đóng gói, cấu hình hoặc hỗ trợ CRaC theo cách khác nhau. Không phải mọi bản phân phối JDK đều có CRaC; cài thêm thư viện Java `org.crac` không tự bổ sung khả năng checkpoint/restore cho một JVM thông thường.

Khi chọn vendor, cần đọc tài liệu của đúng sản phẩm và phiên bản:

- Dòng JDK đó có hỗ trợ CRaC hay không.
- Hệ điều hành và kiến trúc CPU nào được hỗ trợ.
- Phiên bản CRIU, kernel và cấu hình hệ thống nào được yêu cầu.
- Image có thể restore bằng cùng build hay có hỗ trợ một phạm vi build khác.
- Có giới hạn giữa patch update, CPU release, vendor revision hoặc container image không.
- Các tùy chọn JVM, agent và native library nào được hỗ trợ.
- Quy trình xử lý lỗi và cách thu thập log restore.

Không nên kết luận rằng hai JDK tương thích chỉ vì cả hai đều dựa trên OpenJDK, đều dùng HotSpot hoặc đều triển khai API `org.crac`. Cùng nền tảng nguồn không đồng nghĩa với cùng binary build, cấu hình CRaC hoặc điều kiện khôi phục.

### 2.1. Cùng vendor vẫn cần kiểm tra build

Chọn cùng nhà cung cấp là một điều kiện hữu ích để giảm khác biệt, nhưng không phải bảo đảm tuyệt đối. Nhà cung cấp có thể thay đổi cách đóng gói CRaC, bản vá JVM hoặc yêu cầu nền tảng giữa các bản phát hành.

Nếu tài liệu không nêu một dải tương thích rõ ràng, hãy xem **cùng vendor, cùng distribution, cùng phiên bản đầy đủ và cùng build** là cấu hình chuẩn để tạo và restore image. Khi nâng patch hoặc build, tạo image mới bằng runtime mới và chạy lại kiểm thử. Không dùng image cũ với runtime mới chỉ vì cùng vendor.

### 2.2. Khác vendor cần được xem là khác runtime

Một image tạo bởi JDK CRaC của vendor A không được mặc định restore bằng JDK CRaC của vendor B. Hai nhà cung cấp có thể dùng các bản vá, build option, tích hợp native và cách quản lý checkpoint khác nhau.

Chỉ thử cross-vendor restore khi cả hai nhà cung cấp có tài liệu xác nhận rõ cặp phiên bản đó được hỗ trợ. Nếu không có xác nhận, hãy tạo image mới bằng runtime của vendor đích. Việc hai runtime đều chạy cùng ứng dụng không chứng minh chúng có thể đọc và phục hồi cùng snapshot.

## 3. Phân biệt JDK runtime với thư viện `org.crac`

Ứng dụng Java có thể sử dụng API trong package `org.crac`, chẳng hạn:

- `org.crac.Resource` để mô tả lifecycle của tài nguyên.
- `org.crac.Context` để biểu diễn context quản lý resource.
- `org.crac.Core` để truy cập global context.

Dependency Maven `org.crac:crac` cung cấp API Java cho mã ứng dụng. Nó không phải JVM và không thay thế JDK có hỗ trợ CRaC. Cần phân biệt:

| Thành phần | Vai trò | Có tự cung cấp khả năng restore image không? |
|---|---|---|
| CRaC-enabled JDK | JVM và tích hợp checkpoint/restore của runtime | Có, trong phạm vi JDK/nền tảng hỗ trợ |
| `org.crac:crac` | API Java để ứng dụng đăng ký Resource và callback | Không |
| CRIU hoặc cơ chế hệ điều hành tương ứng | Hỗ trợ checkpoint/restore tiến trình ở tầng hệ thống | Không thay thế JVM CRaC |
| Application JAR | Bytecode và tài nguyên ứng dụng | Không |

Phiên bản API có thể ảnh hưởng khả năng biên dịch, method có sẵn và cách ứng dụng đăng ký Resource. Tuy nhiên, API tương thích ở mức source/binary không đồng nghĩa checkpoint image tương thích giữa hai JVM. Hãy quản lý hai câu hỏi riêng:

1. Mã ứng dụng có dùng đúng API `org.crac` mà JDK/framework đã chọn hỗ trợ không?
2. Runtime dùng để restore có nằm trong tập phiên bản được hỗ trợ để đọc image đã tạo không?

Nếu JDK đã cung cấp API theo cách riêng, hãy theo tài liệu của nhà cung cấp để tránh đóng gói lớp trùng hoặc không tương thích. Nếu cần dependency Maven, khóa phiên bản tường minh và kiểm tra dependency tree.

## 4. Các lớp tương thích cần được kiểm tra

Khả năng restore không chỉ phụ thuộc phiên bản JDK. Một image có thể được tạo thành công nhưng thất bại khi chuyển sang host khác vì những điều kiện bên ngoài JVM.

| Lớp tương thích | Thông tin cần ghi nhận | Rủi ro khi khác nhau |
|---|---|---|
| JDK vendor/distribution | Nhà cung cấp và tên distribution | Khác tích hợp CRaC hoặc binary runtime |
| JDK version/build | Phiên bản đầy đủ, build number, revision | Thay đổi cấu trúc runtime hoặc hỗ trợ image |
| JVM options | GC, heap, module, agent và các cờ CRaC | Runtime khởi tạo khác hoặc tùy chọn không tương thích |
| CPU architecture | `amd64`/`x86_64`, `arm64`/`aarch64` | Khác instruction set và binary native |
| OS distribution | Tên và phiên bản Linux | Khác libc, thư viện hệ thống và layout filesystem |
| Kernel | Phiên bản và tính năng được bật | Thiếu khả năng cần cho checkpoint/restore |
| CRIU | Phiên bản và cấu hình | Không đọc/khôi phục được trạng thái hệ thống |
| Native dependencies | JNI, `.so`, agent, driver | Binary hoặc ABI không tương thích |
| Container/runtime | Digest image, container runtime, namespace, cgroup | Khác filesystem, quyền và cấu hình tiến trình |
| Filesystem/mount | Path, volume, quyền và nội dung file | FD hoặc đường dẫn không tồn tại sau restore |
| Network | Interface, address, route, DNS và port | Socket hoặc kết nối ngoài không còn hợp lệ |

Một số thành phần có thể được thay đổi nếu nhà cung cấp hỗ trợ và ứng dụng xử lý tài nguyên đúng cách. Ví dụ, endpoint database có thể được đọc lại sau restore; nhưng điều đó không có nghĩa mọi socket cũ có thể giữ nguyên. Cần phân loại tài nguyên nào được phục hồi bởi engine, tài nguyên nào phải đóng/mở bằng Resource và tài nguyên nào là điều kiện bắt buộc của host.

## 5. Ma trận checkpoint–restore theo phiên bản

Thay vì chỉ ghi một dòng “JDK 21”, hãy lập ma trận cặp runtime tạo image và runtime restore. Ví dụ dưới đây minh họa cấu trúc, không phải bảng xác nhận tương thích của bất kỳ nhà cung cấp cụ thể nào.

| Runtime tạo checkpoint | Runtime restore | Trạng thái ban đầu cần áp dụng |
|---|---|---|
| Vendor A, build X | Vendor A, build X | Cấu hình chuẩn; vẫn phải kiểm thử trên OS/arch đích |
| Vendor A, build X | Vendor A, build Y | Chỉ hỗ trợ nếu tài liệu vendor xác nhận; nếu chưa có bằng chứng thì chưa chấp nhận |
| Vendor A, build X | Vendor A, feature release khác | Không giả định tương thích; cần tài liệu hỗ trợ cụ thể |
| Vendor A, build X | Vendor B, build Z | Không giả định cross-vendor; yêu cầu xác nhận chính thức |
| Vendor A, build X | Cùng JDK nhưng OS/kernel khác | Kiểm tra ma trận nền tảng và chạy restore test |
| Vendor A, build X trên amd64 | Cùng build trên arm64 | Không giả định image portable giữa kiến trúc |

Có thể dùng các trạng thái quản lý:

- `SUPPORTED`: được nhà cung cấp công bố hỗ trợ và đã qua kiểm thử của dự án.
- `TESTED`: dự án đã kiểm thử thành công nhưng chưa có cam kết hỗ trợ chính thức; cần đánh giá rủi ro trước khi dùng production.
- `UNTESTED`: chưa có bằng chứng; không dùng làm cặp runtime chuẩn.
- `UNSUPPORTED`: tài liệu hoặc kiểm thử xác nhận không được hỗ trợ.

Không đánh dấu `SUPPORTED` chỉ dựa trên một lần thử thành công. Một lần restore qua được có thể không bao phủ các điều kiện tải, native dependency, kiến trúc hoặc lỗi xảy ra ở thời điểm khác.

### 5.1. Chính sách mặc định khi chưa có ma trận từ vendor

Nếu tài liệu nhà cung cấp không nêu rõ khả năng restore chéo phiên bản, hãy áp dụng quy tắc bảo thủ:

1. Tạo image bằng một JDK CRaC cụ thể.
2. Restore bằng đúng vendor, distribution, version và build đó.
3. Giữ nguyên kiến trúc, OS/runtime image và các điều kiện hệ thống đã kiểm chứng.
4. Khi nâng JDK, tạo image mới bằng JDK mới.
5. Chỉ mở rộng sang patch/build khác sau khi đọc tài liệu và chạy kiểm thử cặp cụ thể.

Đây là baseline vận hành dễ tái lập. Nếu vendor công bố một dải tương thích rộng hơn, có thể mở rộng ma trận theo đúng điều kiện họ nêu.

## 6. Ghi nhận danh tính runtime khi tạo image

Mỗi image cần có metadata đủ để xác định nó được tạo từ ứng dụng và runtime nào. Không nên chỉ đặt tên thư mục theo version ứng dụng vì nhiều build có thể dùng cùng version nhưng khác commit, JDK hoặc dependency.

Có thể lấy thông tin runtime bằng:

```bash
java -version
java -XshowSettings:properties -version
```

Các thuộc tính hữu ích gồm `java.vendor`, `java.version`, `java.runtime.version`, `java.vm.name`, `java.vm.version`, `java.home` và `os.arch`. Trên Linux, ghi thêm:

```bash
cat /etc/os-release
uname -a
uname -m
ldd --version
criu --version
```

Các lệnh trên giúp nhận diện môi trường đang chạy. Không phải mọi thông tin đều được JVM property cung cấp; cần lưu kết quả từ host hoặc container runtime khi thích hợp.

### 6.1. Ví dụ manifest cho checkpoint image

```yaml
checkpointImage:
  imageId: "orders-api-2.4.0-build-318-amd64"
  application:
    version: "2.4.0"
    gitCommit: "<commit-sha>"
    artifactSha256: "<jar-sha256>"
    dependencyLockSha256: "<lockfile-sha256>"
  jdk:
    vendor: "<vendor-name>"
    distribution: "<crac-enabled-distribution>"
    version: "<full-version>"
    build: "<build-number-or-revision>"
    vmName: "<vm-name>"
    vmVersion: "<vm-version>"
    architecture: "amd64"
  platform:
    os: "<distribution-and-release>"
    kernel: "<kernel-version>"
    libc: "<libc-version>"
    criu: "<criu-version>"
    containerDigest: "sha256:<digest>"
  runtime:
    jvmOptionsHash: "<options-hash>"
    nativeDependencies: "<native-dependency-manifest>"
  checkpoint:
    createdAt: "<timestamp>"
    restoreTestedWith: "<exact-runtime-identity>"
    restoreStatus: "PASS"
```

Các giá trị trong dấu ngoặc nhọn là placeholder, cần thay bằng dữ liệu thực tế. Manifest nên được tạo tự động trong pipeline để tránh nhập sai. Nếu chưa thu thập được một trường, ghi trạng thái chưa biết thay vì tự suy đoán.

### 6.2. Manifest không thay thế kiểm tra tương thích

Manifest cho biết image được tạo từ môi trường nào. Nó không tự chứng minh runtime đích tương thích. Trước khi restore, hệ thống triển khai nên so sánh metadata image với môi trường hiện tại theo chính sách đã được xác nhận.

Ví dụ, nếu image yêu cầu JDK build X nhưng node đang chạy build Y chưa có trong ma trận, deployment nên dừng và yêu cầu tạo image mới hoặc phê duyệt cặp runtime sau khi kiểm thử. Không nên bỏ qua cảnh báo chỉ vì hai runtime cùng Java feature version.

## 7. Container image và host là hai lớp khác nhau

Container image có thể cố định JDK, thư viện hệ thống trong filesystem, application JAR và một số công cụ như CRIU. Tuy nhiên, container dùng kernel của host. Digest của container image không đóng gói toàn bộ kernel hoặc mọi điều kiện cần để restore.

Khi tạo và restore trong container, cần kiểm tra:

- Digest của image chứa JDK và application.
- Container runtime và phiên bản.
- Kernel host và tính năng được CRIU yêu cầu.
- PID, mount, network namespace và cgroup.
- Capability, seccomp, AppArmor hoặc SELinux policy.
- Volume, mount point, đường dẫn file và quyền truy cập.
- Cách nền tảng điều phối cấp network identity và port sau restore.

Nếu image được tạo trên một host Linux rồi restore trong Kubernetes, cần kiểm thử bằng cấu hình gần với pod/node đích. Một container privileged có thể checkpoint thành công trong lab nhưng không có quyền tương tự trong production. Kết quả lab khi đó chưa chứng minh triển khai thật sẽ hoạt động.

## 8. Tương thích của native library và JNI

Ứng dụng có thể dùng thư viện native qua JNI, JNA, agent hoặc driver. Những thành phần này phụ thuộc kiến trúc CPU, ABI, libc, phiên bản binary và trạng thái native tại thời điểm checkpoint.

Ví dụ, một JAR Java có thể giống nhau trên `amd64` và `arm64`, nhưng file `.so` được nạp vào JVM là binary dành riêng cho một kiến trúc. Checkpoint image từ tiến trình đã nạp thư viện đó không thể được xem như artifact portable sang kiến trúc khác.

Khi có native dependency, hãy ghi nhận:

- Tên, phiên bản và checksum của từng binary native.
- Kiến trúc CPU và ABI.
- Phiên bản libc và thư viện hệ thống cần thiết.
- Cách thư viện giải phóng/recreate native handle.
- Có thread native hoặc callback native đang hoạt động khi checkpoint hay không.
- Nhà cung cấp có hỗ trợ checkpoint/restore cho thư viện đó không.

Nếu native component không thể được checkpoint an toàn, cần dùng wrapper/Resource để giải phóng trước checkpoint và tạo lại sau restore, hoặc không đưa component đó vào tiến trình cần checkpoint. Việc Java object được khôi phục không bảo đảm native pointer hoặc handle vẫn hợp lệ.

## 9. Nâng cấp JDK và chiến lược tạo image mới

Nâng JDK có thể thay đổi runtime build, native library, CRaC integration và yêu cầu nền tảng. Vì vậy, nâng JDK cần được xem là thay đổi của chuỗi tạo image.

Quy trình nâng cấp nên gồm:

1. Đọc release notes và tài liệu CRaC của vendor cho bản JDK mới.
2. Xác định yêu cầu mới về OS, kernel, CRIU, architecture và container.
3. Cập nhật JDK build trong build/runtime image và khóa dependency liên quan.
4. Build lại ứng dụng bằng bộ công cụ đã chọn.
5. Khởi chạy ứng dụng bằng JDK mới, chạy warm-up và chuẩn bị Resource.
6. Tạo checkpoint image mới trong thư mục staging riêng.
7. Restore bằng đúng runtime mới và chạy smoke test.
8. Nếu cần hỗ trợ restore chéo version, kiểm thử từng cặp checkpoint–restore theo ma trận và xác nhận vendor support.
9. Chỉ công bố image mới sau khi restore, readiness và kiểm thử nghiệp vụ thành công.
10. Giữ image cũ cùng runtime cũ trong thời gian rollback còn cần thiết.

Không thay JDK trong container rồi tiếp tục dùng checkpoint image cũ mà không có xác nhận tương thích. Image mới nên được tạo từ tiến trình chạy đúng build ứng dụng và runtime mới.

### 9.1. Rollback cũng cần đúng runtime

Giữ checkpoint image cũ mà không giữ runtime tương ứng có thể làm rollback không thực hiện được. Artifact rollback cần đi cùng bộ JDK/container/host configuration đã tạo và restore thành công image đó.

Một bản phát hành có thể lưu cặp:

```text
release-2.3/
  application.jar
  runtime-manifest.yml
  container-image-digest.txt
  checkpoint-image/

release-2.4/
  application.jar
  runtime-manifest.yml
  container-image-digest.txt
  checkpoint-image/
```

Đường dẫn chỉ minh họa cách tổ chức. Mục tiêu là giữ artifact và runtime identity liên kết với nhau. Khi rollback, triển khai đồng bộ image cùng môi trường tương thích đã được kiểm chứng.

## 10. Kiểm thử tương thích theo ma trận

Một lần checkpoint và restore bằng cùng runtime chỉ xác nhận baseline đó hoạt động. Nếu dự án muốn hỗ trợ nâng patch, đổi host hoặc đổi vendor, cần thử từng tổ hợp có chủ đích.

### 10.1. Các cặp cần kiểm tra

| Kịch bản | Mục tiêu |
|---|---|
| Tạo và restore bằng cùng JDK build | Xác nhận baseline runtime |
| Tạo bằng build X, restore bằng build Y cùng vendor | Xác nhận phạm vi patch/build theo tài liệu vendor |
| Tạo và restore bằng hai feature release khác nhau | Xác định có được hỗ trợ hay không; không mặc định thành công |
| Tạo bằng vendor A, restore bằng vendor B | Chỉ kiểm tra nếu có tuyên bố hỗ trợ cross-vendor |
| Cùng JDK, đổi Linux distribution/kernel | Kiểm tra phụ thuộc hệ thống và CRIU |
| Cùng JDK/OS, đổi kiến trúc CPU | Xác nhận giới hạn kiến trúc; không giả định portability |
| Cùng runtime, đổi container digest | Kiểm tra native dependencies, filesystem và cấu hình |
| Restore sau khi image được lưu lâu | Kiểm tra secret, certificate, DNS, lease và dependency ngoài |

Không cần thử mọi tổ hợp có thể tưởng tượng. Hãy chọn các cặp cần hỗ trợ trong production, các cặp nằm trong kế hoạch nâng cấp và một số cặp âm để xác nhận hệ thống từ chối môi trường không hợp lệ.

### 10.2. Các bước trong smoke test

1. In và lưu danh tính JDK, vendor, version, build và VM.
2. Lưu OS, kernel, architecture, CRIU và container digest.
3. Khởi chạy application build đã xác định.
4. Thực hiện warm-up và đăng ký Resource.
5. Yêu cầu checkpoint và xác nhận image được tạo đầy đủ.
6. Restore bằng runtime đích trong ma trận.
7. Xác nhận callback `afterRestore` đã chạy.
8. Kiểm tra database, HTTP client, message consumer và tài nguyên bắt buộc.
9. Chạy health/readiness check và một số request nghiệp vụ đại diện.
10. Ghi thời gian restore, thời gian đến readiness, log và kết quả.

Nếu restore thất bại, lưu toàn bộ log của JVM và CRIU cùng metadata hai môi trường. Không chỉ lưu thông báo lỗi cuối cùng vì nguyên nhân có thể xuất hiện ở bước kiểm tra image, khôi phục memory, mở lại FD hoặc callback ứng dụng.

### 10.3. Kiểm thử từ chối cặp không được hỗ trợ

Pipeline cũng nên chứng minh hệ thống không triển khai nhầm image. Ví dụ, nếu manifest ghi JDK build X nhưng node chỉ có build Y chưa được phê duyệt, bước kiểm tra trước restore phải từ chối deployment và chỉ rõ khác biệt.

Việc từ chối sớm giúp tránh thử restore trên môi trường không được hỗ trợ và làm rõ lỗi cấu hình trước khi instance tham gia rollout.

## 11. Chẩn đoán lỗi tương thích

Lỗi restore có thể xuất hiện ở nhiều tầng. Cần đối chiếu lỗi với metadata tạo image và runtime đích.

| Dấu hiệu | Nhóm nguyên nhân cần kiểm tra |
|---|---|
| Runtime từ chối image hoặc báo version mismatch | JDK vendor, build, format hoặc phiên bản CRaC |
| Lỗi liên quan CRIU hoặc kernel | Phiên bản CRIU, kernel feature, capability, namespace, cgroup |
| Lỗi load native library | Kiến trúc, ABI, libc, đường dẫn `.so`, phiên bản binary |
| Lỗi mở file hoặc descriptor | Path, mount, quyền, file đã thay đổi hoặc FD policy |
| Lỗi socket/network | Network namespace, interface, address, route, peer hoặc tài nguyên chưa được recreate |
| Callback `afterRestore` thất bại | Dependency ngoài, credential, factory, thứ tự Resource hoặc logic phục hồi |
| Restore thành công nhưng readiness thất bại | Application state, database, cache, message broker hoặc cấu hình runtime |

Một số nguyên tắc điều tra:

- So sánh manifest của image với runtime thực tế, không dựa vào nhãn container hoặc tên JDK rút gọn.
- Xác nhận đúng executable `java` được dùng để restore bằng `java -version` và `java.home`.
- Kiểm tra log của JVM và CRIU ở cùng một lần chạy.
- Kiểm tra quyền, namespace và mount trên host thực tế.
- Phân biệt lỗi do runtime từ chối image với lỗi do callback ứng dụng sau khi restore.
- Không khắc phục bằng cách bỏ qua version check hoặc thay đổi binary trong thư mục image.

## 12. Quản lý image theo runtime identity

Checkpoint image cần được quản lý như artifact có phiên bản. Đặt tên image theo application build là chưa đủ; nên liên kết thêm runtime identity và kiến trúc.

Ví dụ cấu trúc:

```text
artifacts/
  orders-api/
    2.4.0/
      commit-a81f2d1/
        linux-amd64/
          vendor-a-jdk-21.0.x-build-123/
            checkpoint-image/...
            manifest.yml
            restore-test.log
      2.4.1/
        commit-b42c9e0/
          linux-amd64/
            vendor-a-jdk-21.0.y-build-127/
              checkpoint-image/...
              manifest.yml
              restore-test.log
```

Đây là ví dụ định danh, không phải tên phiên bản JDK thực tế. Mỗi thư mục checkpoint cần được tạo riêng cho một lần tạo image. Không ghi đè image đang được production dùng; tạo image mới, restore thử và công bố bằng định danh bất biến.

Chính sách retention cần giữ các image còn được deployment tham chiếu và các bản cần cho rollback. Khi xóa image cũ, xóa cả metadata liên quan theo chính sách nhưng không xóa runtime artifact còn cần để phục hồi bản phát hành đang được giữ.

## 13. Những sai lầm thường gặp

**Chỉ so sánh Java major version.** Cùng Java 21 không chứng minh hai JDK có cùng build hoặc hỗ trợ cùng image. Ghi nhận vendor, distribution, version đầy đủ và build.

**Cho rằng cùng vendor luôn tương thích.** Vendor có thể thay đổi runtime và quy tắc CRaC giữa các bản phát hành. Kiểm tra ma trận chính thức và kiểm thử build cụ thể.

**Cho rằng mọi JDK dựa trên OpenJDK đều có thể restore lẫn nhau.** Tích hợp CRaC và binary runtime có thể khác nhau. Không giả định cross-vendor nếu không có xác nhận.

**Nhầm API `org.crac` với CRaC-enabled JVM.** Dependency API giúp mã ứng dụng biên dịch và đăng ký Resource; nó không bổ sung checkpoint/restore cho JDK thông thường.

**Chỉ pin container digest.** Digest không cố định kernel host, namespace, capability hoặc mọi điều kiện CRIU. Phải kiểm tra cả host.

**Bỏ qua kiến trúc CPU.** Image và native library có thể phụ thuộc `amd64` hoặc `arm64`. Xây dựng và kiểm thử riêng từng kiến trúc.

**Nâng JDK nhưng tái sử dụng image cũ.** Image cũ vẫn chứa trạng thái runtime trước đó. Tạo image mới bằng JDK mới trừ khi vendor xác nhận cặp phiên bản được hỗ trợ.

**Chỉ kiểm tra checkpoint thành công.** Image tạo được chưa chứng minh restore thành công. Luôn chạy restore và kiểm tra readiness.

**Đánh dấu một cặp là được hỗ trợ sau một lần thử.** Kết quả thử nghiệm không thay thế tuyên bố hỗ trợ của vendor. Ghi rõ `TESTED` hay `SUPPORTED` và bằng chứng tương ứng.

**Giữ image rollback nhưng xóa runtime tương ứng.** Rollback có thể không còn thực hiện được. Lưu cặp image–runtime cùng nhau.

## 14. Tự kiểm tra mức độ hiểu

1. **Vì sao cùng Java feature version chưa đủ để kết luận checkpoint image tương thích?** Vì vendor, distribution, update, build và tích hợp CRaC có thể khác nhau.
2. **Có thể mặc định restore image của vendor A bằng vendor B không?** Không. Chỉ làm khi cả hai bên xác nhận cặp runtime đó được hỗ trợ và dự án đã kiểm thử.
3. **`org.crac:crac` có cung cấp khả năng checkpoint cho JDK thông thường không?** Không. Nó cung cấp API Java; checkpoint/restore cần runtime và nền tảng hỗ trợ.
4. **Vì sao cần ghi build number của JDK vào manifest?** Để nhận diện chính xác runtime đã tạo image và đối chiếu với runtime đích.
5. **Container digest có cố định kernel không?** Không. Container dùng kernel host, nên cần ghi và kiểm tra kernel cùng điều kiện CRIU.
6. **Khi nâng JDK nên làm gì với checkpoint image?** Tạo image mới từ ứng dụng chạy trên JDK mới và restore thử bằng runtime đích.
7. **`SUPPORTED` khác `TESTED` như thế nào?** `SUPPORTED` có tài liệu hỗ trợ chính thức cùng kiểm thử dự án; `TESTED` chỉ thể hiện dự án đã thử thành công nhưng chưa có cam kết hỗ trợ tương ứng.
8. **Vì sao rollback cần giữ runtime cũ?** Vì image cũ có thể chỉ restore được trên bộ JDK và môi trường đã tạo ra nó hoặc cặp được vendor xác nhận.

## Kết luận

Checkpoint image gắn với trạng thái của một tiến trình và runtime đã tạo ra nó. Khả năng restore phụ thuộc vào vendor, distribution, phiên bản đầy đủ, build JDK, kiến trúc CPU, hệ điều hành, kernel, CRIU, container/runtime và native dependencies. Cùng Java feature version hoặc cùng API `org.crac` không đủ để chứng minh hai môi trường tương thích.

Hãy chọn một bộ runtime chuẩn, lưu manifest chi tiết cùng image và lập ma trận cho từng cặp checkpoint–restore. Khi chưa có tài liệu xác nhận tương thích chéo phiên bản, dùng đúng JDK build đã tạo image làm baseline. Mọi nâng cấp JDK hoặc thay đổi nền tảng cần tạo image mới và chạy restore test trên môi trường đích. Giữ image rollback cùng runtime tương ứng để quá trình phát hành và phục hồi có thể tái lập.
