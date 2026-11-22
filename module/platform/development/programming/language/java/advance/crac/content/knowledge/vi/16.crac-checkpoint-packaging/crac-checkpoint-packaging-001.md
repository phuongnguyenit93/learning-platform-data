# Phân biệt ảnh checkpoint, JAR ứng dụng và container image

Trong một ứng dụng Java dùng CRaC (Coordinated Restore at Checkpoint), có ba loại artifact thường được gọi chung là “image”: JAR ứng dụng, container image và checkpoint image. Chúng phục vụ ba mục đích khác nhau.

- **JAR ứng dụng** đóng gói mã Java, resource và metadata cần để chạy chương trình.
- **Container image** đóng gói filesystem, JDK/runtime, thư viện hệ thống và cấu hình mặc định để tạo container.
- **Checkpoint image** lưu trạng thái của một tiến trình Java đang chạy tại một thời điểm, để runtime tương thích có thể khôi phục tiến trình đó.

Một JAR có thể chạy trên nhiều môi trường Java tương thích. Container image có thể tạo ra nhiều container từ cùng một filesystem image. Checkpoint image lại gắn chặt với trạng thái tiến trình và môi trường đã tạo ra nó. Vì vậy, không thể thay thế ba artifact này cho nhau hoặc giả định chúng có cùng mức độ di động.

Bài này giải thích nội dung, vòng đời, quan hệ phụ thuộc và cách đóng gói ba loại artifact khi triển khai Java CRaC.

## 1. Ba loại artifact giải quyết ba bài toán

### 1.1 JAR ứng dụng: đóng gói chương trình

JAR (Java Archive) là định dạng archive dựa trên ZIP. JAR thường chứa:

- Java bytecode đã biên dịch thành file .class.
- Resource như properties, YAML, template, schema hoặc file tĩnh.
- Metadata trong META-INF.
- Manifest mô tả entry point hoặc thông tin archive.
- Dependency nếu dùng executable/fat/uber JAR.

Một JAR chạy được thường có manifest với Main-Class, hoặc được khởi chạy bằng framework launcher. Ví dụ:

~~~bash
java -jar application.jar
~~~

JAR mô tả chương trình cần chạy. Nó không lưu heap hiện tại, thread stack, trạng thái kết nối, cache đã warm-up hay vị trí thực thi của một JVM đang hoạt động.

Nếu ứng dụng đã chạy 20 phút, JAR vẫn là cùng một file như trước khi chạy. Trạng thái mà chương trình tích lũy trong bộ nhớ không được ghi ngược vào JAR.

### 1.2 Container image: đóng gói môi trường chạy

Container image là một filesystem image theo định dạng OCI hoặc định dạng tương thích runtime. Nó thường bao gồm:

- Base operating system hoặc root filesystem tối thiểu.
- JDK/JRE và các runtime library.
- JAR ứng dụng và dependency.
- CA certificate, timezone data và thư viện native.
- User, working directory, entrypoint và metadata container.
- Cấu hình mặc định không chứa bí mật môi trường.

Container image được dùng để tạo container. Nhiều container có thể được tạo từ cùng một image nhưng có PID, network namespace, writable layer, volume và cấu hình runtime riêng.

Container image không tự chứa trạng thái heap của một JVM đã khởi chạy. Nó mô tả filesystem và cách khởi động container, không phải trạng thái thực thi đầy đủ của một process cụ thể.

### 1.3 Checkpoint image: đóng gói trạng thái tiến trình

Checkpoint image là artifact được tạo bởi CRaC runtime phối hợp với checkpoint engine. Nó lưu trạng thái cần thiết để khôi phục tiến trình tại một thời điểm, có thể bao gồm:

- Java heap và các object đang được tham chiếu.
- Trạng thái thread và vị trí thực thi theo khả năng của engine.
- Native memory và các vùng địa chỉ tiến trình được hỗ trợ.
- Trạng thái runtime cần thiết để tiếp tục thực thi.
- Thông tin mapping và tài nguyên tiến trình mà engine quản lý.

Trước khi tạo ảnh, CRaC gọi các Resource callback để ứng dụng chuẩn bị. Sau khi restore, callback phục hồi tài nguyên như file, socket, connection pool hoặc client bên ngoài.

Checkpoint image không phải một JAR khác và cũng không phải một container image theo nghĩa thông thường. Nó phụ thuộc vào runtime, engine và môi trường đã tạo ra nó.

## 2. So sánh trực tiếp

| Tiêu chí | JAR ứng dụng | Container image | Checkpoint image |
|---|---|---|---|
| Mục đích | Đóng gói chương trình Java | Đóng gói filesystem và môi trường chạy | Lưu trạng thái tiến trình đang chạy |
| Nội dung chính | Class, resource, manifest, dependency | Root filesystem, JDK, thư viện, app artifact, metadata | Heap, thread/process state, native memory và trạng thái được engine hỗ trợ |
| Được tạo khi nào | Sau compile/package | Khi build container image | Khi tiến trình đang chạy yêu cầu checkpoint |
| Cách sử dụng | Khởi động JVM mới | Tạo container rồi khởi động entrypoint | Tiếp tục process từ ảnh |
| Có chứa heap đã warm-up? | Không | Không, trừ khi được lưu riêng như artifact | Có, trong phạm vi engine hỗ trợ |
| Có chứa JAR ứng dụng? | Chính nó là JAR | Có thể chứa JAR | Không nên xem checkpoint là bản thay thế JAR; cần giữ JAR/build tương ứng |
| Tính di động | Tương đối cao giữa JDK tương thích | Phụ thuộc OS/architecture và runtime | Hạn chế, gắn với build và môi trường tương thích |
| Thay đổi code | Build JAR mới | Build container image mới hoặc cập nhật layer | Thông thường phải tạo checkpoint mới |
| Khởi động | Tạo JVM mới | Tạo container và process mới | Tiếp tục process từ ảnh |
| Nguồn trạng thái | Source code và build | Dockerfile/build context và base image | Trạng thái runtime tại thời điểm checkpoint |

Có thể nhớ bằng ba câu:

- JAR trả lời: **chương trình là gì?**
- Container image trả lời: **chương trình chạy trong môi trường nào?**
- Checkpoint image trả lời: **tiến trình đang ở trạng thái nào?**

## 3. Mối quan hệ giữa ba loại image

Một quy trình Java CRaC thường bắt đầu bằng JAR, đưa JAR vào container image, sau đó khởi động container để tạo checkpoint image.

~~~mermaid
flowchart TD
    A["Source code + dependencies"] --> B["Build application JAR"]
    B --> C["Build container image<br/>JDK + OS libraries + JAR"]
    C --> D["Start container and JVM"]
    D --> E["Application startup and warm up"]
    E --> F["CRaC beforeCheckpoint callbacks"]
    F --> G["Create checkpoint image"]
    G --> H["Store checkpoint artifact<br/>with compatible container digest"]
    H --> I["Create compatible container"]
    I --> J["Restore checkpoint image"]
    J --> K["CRaC afterRestore callbacks"]
    K --> L["Validate dependencies and serve"]
~~~

JAR và container image vẫn cần được quản lý ngay cả khi checkpoint image đã được tạo. Nếu checkpoint không thể restore do lỗi môi trường, ứng dụng cần có khả năng khởi động mới từ JAR bên trong container image.

Checkpoint image cũng cần được gắn với đúng container image hoặc một môi trường tương thích. Không nên lấy checkpoint của một build rồi tùy ý ghép với JDK hoặc thư viện hệ thống của build khác.

### 3.1 Artifact nào là nguồn gốc?

Một chuỗi build có thể có quan hệ như sau:

~~~text
Source revision
   |
   v
Application JAR
   |
   v
Container image digest
   |
   v
Running JVM
   |
   v
Checkpoint image
~~~

- Source revision xác định code.
- JAR hash xác định binary và resource.
- Container digest xác định filesystem image.
- Checkpoint ID xác định một lần chụp trạng thái tiến trình.

Checkpoint image là kết quả phát sinh từ một container image cụ thể và một lần chạy cụ thể. Metadata cần giữ mối liên hệ này để triển khai, rollback và chẩn đoán.

## 4. JAR không thể thay thế checkpoint image

Giả sử một ứng dụng cần 30 giây để khởi động, kết nối database, nạp cache và warm-up JIT.

Khi chạy từ JAR:

1. JVM khởi động.
2. Class được load.
3. Application context được tạo.
4. Database connection pool được khởi tạo.
5. Cache được nạp.
6. Các đường xử lý quan trọng được warm-up.
7. Ứng dụng chuyển sang trạng thái sẵn sàng.

JAR chỉ chứa chương trình và resource để thực hiện những bước này. Mỗi lần chạy JAR, các bước khởi động sẽ được thực hiện theo logic ứng dụng.

Với CRaC, có thể tạo checkpoint sau khi warm-up. Khi restore, tiến trình tiếp tục từ trạng thái đã được lưu thay vì thực hiện lại toàn bộ startup path.

Điều này có thể giảm thời gian khởi động, nhưng không làm JAR trở nên dư thừa:

- JAR vẫn là binary cần để khởi động mới.
- JAR là nguồn xác định code tương ứng với checkpoint.
- JAR được dùng để tạo checkpoint mới khi code thay đổi.
- JAR hỗ trợ fallback nếu checkpoint image không tương thích hoặc không thể restore.
- JAR có thể được dùng để chạy test hoặc triển khai không sử dụng CRaC.

Không nên đổi tên file checkpoint thành .jar hoặc đưa checkpoint image vào classpath. Checkpoint image không phải Java archive và không thể được nạp bằng java -jar.

## 5. Container image không đồng nghĩa checkpoint image

Container image mô tả filesystem và metadata của môi trường chạy. Checkpoint image lưu trạng thái tiến trình đang chạy trong môi trường đó.

Một container image có thể được dùng để:

- Khởi động JVM mới từ JAR.
- Tạo một container làm nguồn để warm-up và checkpoint.
- Tạo container tương thích để restore checkpoint.
- Chạy cùng JAR mà không dùng checkpoint nếu deployment chọn chế độ startup thông thường.

Checkpoint image có thể được lưu trong filesystem của container, volume, object storage hoặc một kho artifact riêng tùy engine và quy trình triển khai.

Điều quan trọng là container được dùng để restore phải có runtime và filesystem tương thích với checkpoint. Chỉ cùng tên tag container là chưa đủ nếu tag có thể bị ghi đè. Nên liên kết checkpoint với digest bất biến của container image.

### 5.1 OCI image và process checkpoint là hai khái niệm khác nhau

OCI image là một định dạng đóng gói filesystem và metadata cho container runtime. Process checkpoint là trạng thái của tiến trình được checkpoint engine ghi lại.

Một số nền tảng có thể hỗ trợ đóng gói checkpoint artifact cùng OCI artifact hoặc tạo một container image mới chứa checkpoint files. Đây là lựa chọn triển khai và phụ thuộc tooling. Không có nghĩa checkpoint image tự động trở thành OCI image chuẩn hoặc có thể được chạy như một container image thông thường.

Cũng cần phân biệt CRaC với tính năng checkpoint/restore container ở cấp container runtime. CRaC cung cấp API để ứng dụng Java phối hợp dừng và phục hồi tài nguyên. Container runtime checkpoint có thể chụp trạng thái container/process ở tầng thấp hơn. Hai cơ chế có mục tiêu và lifecycle khác nhau; không nên xem chúng là cùng một thao tác.

## 6. Nội dung và mức độ phụ thuộc của checkpoint image

Checkpoint image có thể chứa nhiều trạng thái runtime mà JAR và container image không có.

### 6.1 Java heap

Heap có thể chứa:

- Application context và object graph.
- Cache đã nạp.
- Metadata và cấu trúc dữ liệu.
- Kết quả parse hoặc tính toán đã warm-up.
- Một số trạng thái framework và thư viện.

Các object này giúp giảm công việc khởi tạo sau restore. Tuy nhiên, cache có thể cũ và object có thể giữ tham chiếu tới tài nguyên bên ngoài đã thay đổi.

### 6.2 Thread và trạng thái thực thi

Checkpoint engine phải lưu trạng thái cần thiết để khôi phục thread và tiếp tục thực thi. CRaC callback giúp ứng dụng đưa thread và tài nguyên về điểm an toàn trước khi tạo ảnh.

Không nên giả định mọi thread state hoặc mọi native thread đều được hỗ trợ trong mọi engine. Cần theo tài liệu của JDK build và checkpoint engine.

### 6.3 Native memory và file mapping

Direct buffer, native allocation, memory mapping và JNI resource có thể ảnh hưởng tới checkpoint. Một số vùng nhớ có thể được lưu như memory pages, nhưng file-backed mapping và native handle còn phụ thuộc filesystem, kernel và engine.

### 6.4 File descriptor và kết nối

Socket, database session, file descriptor và các tài nguyên kernel không đơn giản là dữ liệu heap. Ứng dụng thường cần đóng trước checkpoint và tạo lại sau restore bằng Resource callback.

### 6.5 Dữ liệu nhạy cảm

Heap có thể chứa:

- Access token và refresh token.
- Password hoặc secret đã giải mã.
- Session state.
- Private key hoặc credential cache.
- Dữ liệu người dùng đang xử lý.

Vì checkpoint image lưu trạng thái tiến trình, nó có thể chứa dữ liệu nhạy cảm ngay cả khi container image và JAR không chứa secret. Cần bảo vệ checkpoint artifact như một bản sao dữ liệu runtime có độ nhạy cao.

## 7. Độ di động và điều kiện tương thích

JAR, container image và checkpoint image có mức độ di động khác nhau.

### 7.1 JAR

JAR có thể chạy trên các JDK tương thích với bytecode, API và dependency mà ứng dụng sử dụng. Một JAR được build bằng Java 17 có thể chạy trên JDK mới hơn nếu không phụ thuộc hành vi hoặc API không tương thích, nhưng điều đó không tự động đúng với mọi thư viện.

JAR không chứa native code của hệ điều hành theo mặc định. Nếu ứng dụng phụ thuộc JNI, native library vẫn cần đúng OS, architecture và ABI.

### 7.2 Container image

Container image thường gắn với OS userland và architecture. Image Linux amd64 không thể mặc định chạy trên host arm64 nếu không có multi-arch manifest hoặc cơ chế emulation phù hợp.

Container image có thể chạy trên nhiều kernel host tương thích, nhưng vẫn phụ thuộc system call, CPU feature, driver, security policy và container runtime.

### 7.3 Checkpoint image

Checkpoint image thường có phạm vi tương thích hẹp hơn. Cần kiểm tra ít nhất:

| Thành phần | Vì sao quan trọng |
|---|---|
| JDK vendor và build | Cấu trúc nội bộ JVM và CRaC integration có thể khác |
| JDK version | Heap/runtime metadata và implementation thay đổi theo phiên bản |
| CRaC API/runtime | Resource callback và hành vi checkpoint/restore phụ thuộc runtime |
| Checkpoint engine | Cách lưu và khôi phục process state khác nhau |
| OS và kernel | Process state, syscall, VMA và tài nguyên kernel phụ thuộc hệ điều hành |
| CPU architecture | Register, instruction set và native code phụ thuộc kiến trúc |
| CPU features | Một số build hoặc native library yêu cầu feature cụ thể |
| Native libraries và ABI | Thư viện được nạp trong process cần tương thích |
| Filesystem và mount | File-backed mapping, đường dẫn và quyền có thể ảnh hưởng restore |
| Runtime configuration | Heap, flags, environment và cấu hình engine có thể cần giống lúc checkpoint |
| External dependencies | Database, DNS, secret, service endpoint phải được xác minh lại |

Một checkpoint image được tạo trên môi trường development không mặc nhiên có thể restore trên production. Cần tạo và thử image trong môi trường gần với nơi sẽ restore.

### 7.4 Multi-architecture

Nếu triển khai cả amd64 và arm64, không nên dùng một checkpoint artifact chung cho cả hai kiến trúc. Hãy tạo checkpoint riêng từ từng runtime/architecture tương ứng và gắn metadata rõ ràng.

Container image có thể có manifest đa kiến trúc, nhưng checkpoint artifact vẫn cần được phân loại theo kiến trúc và build thực tế.

## 8. Đóng gói JAR trong container image

Một Dockerfile multi-stage có thể build JAR ở stage đầu và đưa artifact vào runtime image ở stage sau.

Ví dụ:

~~~dockerfile
# Stage 1: build ứng dụng
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -DskipTests package

# Stage 2: runtime có CRaC
FROM <crac-enabled-jdk-runtime-image>
WORKDIR /app

COPY --from=build /workspace/target/application.jar /app/application.jar

USER 10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

CRAC-ENABLED-JDK-RUNTIME-IMAGE trong ví dụ là placeholder cho base image có CRaC runtime và checkpoint engine phù hợp với môi trường triển khai. Không phải mọi image Temurin hoặc OpenJDK đều có checkpoint engine thực.

Stage build có thể dùng JDK thông thường nếu chỉ cần compile, nhưng runtime stage phải cung cấp JDK/CRaC build tương thích để tạo và restore checkpoint.

### 8.1 Tách build stage và runtime stage

Multi-stage build giúp:

- Không đưa Maven, Gradle hoặc source code vào runtime image nếu không cần.
- Giảm kích thước image.
- Tách dependency build khỏi dependency runtime.
- Kiểm soát JDK được dùng khi chạy CRaC.

Nếu ứng dụng dùng JNI hoặc thư viện native, runtime stage vẫn phải chứa các thư viện runtime tương ứng. Không copy nhầm binary chỉ có trong build stage mà runtime stage không có.

### 8.2 Pin base image

Không nên chỉ dùng tag mutable như latest cho runtime image. Hãy pin version và digest của base image trong quy trình build để biết chính xác JDK, thư viện và filesystem nào đã tạo checkpoint.

Khi base image được cập nhật, cần đánh giá lại checkpoint compatibility. Một container image mới dù chỉ thay JDK patch version hoặc native library cũng có thể không tương thích với checkpoint cũ theo bảo đảm của vendor.

## 9. Quy trình tạo checkpoint artifact

Checkpoint nên được tạo từ một tiến trình đã chạy trong đúng runtime/container image dự kiến sử dụng.

Một quy trình điển hình:

1. Build JAR.
2. Build container image có CRaC-enabled JDK.
3. Khởi chạy container trong môi trường tương thích.
4. Chờ startup hoàn tất.
5. Khởi tạo dependency và chạy warm-up.
6. Đưa ứng dụng tới trạng thái checkpoint-ready.
7. CRaC gọi beforeCheckpoint để dừng công việc và giải phóng tài nguyên cần thiết.
8. Checkpoint engine tạo image.
9. Lưu checkpoint artifact và metadata tương ứng.
10. Kiểm thử restore trong container tương thích.

~~~mermaid
sequenceDiagram
    participant CI as Build Pipeline
    participant Registry as Artifact Registry
    participant Container as Runtime Container
    participant CRaC as CRaC Runtime
    participant Store as Checkpoint Store

    CI->>CI: Build application JAR
    CI->>CI: Build container image
    CI->>Registry: Push JAR/container artifacts
    Registry-->>Container: Pull exact image digest
    Container->>Container: Start JVM and warm up
    Container->>CRaC: Request checkpoint
    CRaC->>Container: beforeCheckpoint callbacks
    CRaC->>Store: Write checkpoint files
    Store-->>CI: Checkpoint artifact + metadata
    CI->>Store: Publish immutable checkpoint version
~~~

Chi tiết tạo checkpoint, vị trí output và cách export phụ thuộc JDK vendor, engine và nền tảng. Không nên giả định một lệnh hoặc một thư mục checkpoint giống nhau trên mọi build.

### 9.1 Vì sao không chỉ chạy checkpoint trong Dockerfile?

Một Dockerfile tiêu chuẩn chủ yếu tạo filesystem layers. RUN thường thực thi trong một build container tạm thời; tiến trình có thể không tồn tại trong runtime context mà production dùng để restore.

Checkpoint phụ thuộc process state, kernel, engine, filesystem và môi trường. Vì vậy, tạo checkpoint thường là một bước riêng trong pipeline hoặc một workflow chạy container thực tế, thay vì xem nó như kết quả build JAR đơn thuần.

Một số nền tảng có quy trình build checkpoint image chuyên biệt. Nếu sử dụng, hãy làm theo tooling của nền tảng và giữ mối liên hệ với base image digest.

## 10. Cách lưu trữ và liên kết artifact

Có nhiều cách lưu checkpoint artifact:

- Thư mục artifact trong workspace build.
- Volume hoặc filesystem được chia sẻ.
- Object storage.
- Artifact registry hỗ trợ loại artifact phù hợp.
- OCI artifact hoặc container image layer theo tooling của nền tảng.

Không phải registry nào cũng hiểu checkpoint image như một artifact có thể restore. Nếu lưu checkpoint trong một container image mới, vẫn cần metadata và quy trình restore tương ứng.

### 10.1 Dùng immutable identifier

Một checkpoint artifact nên có định danh bất biến, chẳng hạn:

~~~text
application: orders-service
build: 2.8.1
jar-sha256: <digest>
container-digest: sha256:<digest>
jdk-build: <vendor-version-build>
engine: <engine-version>
architecture: linux-amd64
checkpoint-id: <unique-id>
created-at: <timestamp>
~~~

Các giá trị trong dấu ngoặc nhọn là placeholder. Metadata này giúp xác định checkpoint được tạo từ code, runtime và môi trường nào.

Không dùng lại cùng một tên file rồi ghi đè checkpoint cũ. Version bất biến giúp rollback, kiểm toán và so sánh kết quả restore.

### 10.2 Ví dụ manifest metadata

~~~json
{
  "application": "orders-service",
  "applicationVersion": "2.8.1",
  "jarSha256": "sha256:...",
  "containerImage": "registry.example/orders@sha256:...",
  "jdk": {
    "vendor": "example-vendor",
    "version": "21.x",
    "build": "crac-build-id"
  },
  "checkpointEngine": {
    "name": "engine-name",
    "version": "engine-version"
  },
  "platform": {
    "os": "linux",
    "architecture": "amd64"
  },
  "checkpointId": "orders-2.8.1-linux-amd64-001",
  "createdAt": "2026-11-13T06:00:00Z"
}
~~~

Đây là schema minh họa do pipeline định nghĩa, không phải format bắt buộc của CRaC. Có thể bổ sung kernel, CPU features, config revision, schema compatibility, image checksum và danh sách external dependency.

### 10.3 Gắn checkpoint với container digest

Nếu checkpoint được tạo từ container image digest sha256:abc..., hãy lưu digest đó trong metadata. Khi restore, pull đúng image digest hoặc image đã được chứng minh tương thích.

Không dựa vào tag orders-service:latest vì tag có thể trỏ tới một image khác sau lần build tiếp theo.

## 11. Quy trình restore

Restore thường bắt đầu bằng việc tạo container tương thích, cung cấp checkpoint files và gọi cơ chế restore của runtime/engine.

Luồng khái quát:

~~~text
Select checkpoint artifact
   |
   v
Read checkpoint metadata
   |
   v
Verify application and runtime compatibility
   |
   v
Pull exact compatible container image
   |
   v
Prepare required mounts and environment
   |
   v
Restore process from checkpoint
   |
   v
Run afterRestore callbacks
   |
   v
Reconcile external state
   |
   v
Mark application ready
~~~

Cần phân biệt các giai đoạn:

- **Container creation:** tạo môi trường filesystem và namespace.
- **Process restore:** khôi phục trạng thái JVM từ checkpoint.
- **Resource recovery:** chạy callback afterRestore để mở lại tài nguyên.
- **External reconciliation:** đọc lại cấu hình, secret, schema, lease và trạng thái dịch vụ hiện tại.
- **Readiness:** chỉ mở traffic khi các điều kiện bắt buộc đã đạt.

Một container có thể đã được tạo thành công nhưng process restore vẫn thất bại. Process restore có thể thành công nhưng callback afterRestore vẫn lỗi. JVM đã chạy lại cũng chưa đồng nghĩa ứng dụng sẵn sàng phục vụ.

## 12. Giữ đường khởi động mới làm fallback

Checkpoint artifact có thể không dùng được vì:

- Runtime hoặc engine không tương thích.
- Checkpoint bị hỏng hoặc thiếu file.
- Kernel hoặc CPU khác yêu cầu.
- External file backing không tồn tại.
- Secret hoặc dependency không thể phục hồi.
- Resource callback thất bại.
- Ứng dụng đã có phiên bản mới và image cũ bị thu hồi.

Một hệ thống triển khai nên có đường fallback chạy JAR từ container image tương thích.

~~~mermaid
flowchart TD
    A["Deployment requests instance"] --> B["Validate checkpoint metadata"]
    B --> C{"Checkpoint compatible?"}
    C -->|Yes| D["Attempt restore"]
    C -->|No| G["Fresh JVM startup from JAR"]
    D --> E{"Restore and callbacks successful?"}
    E -->|Yes| F["Reconcile and mark ready"]
    E -->|No| G
    G --> H["Run startup, migration policy and warm up"]
    H --> I["Mark ready"]
~~~

Fallback cần được thiết kế cẩn thận. Nếu restore đã thực hiện một số side effect trước khi thất bại, việc khởi động mới có thể chạy lại chúng. Migration, seed và nghiệp vụ cần có cơ chế idempotent hoặc trạng thái bền vững.

Không nên retry restore vô hạn với cùng checkpoint artifact đã biết là không tương thích. Hãy ghi nhận nguyên nhân và chuyển sang fallback hoặc tạo checkpoint mới.

## 13. Quản lý phiên bản và invalidation

Checkpoint image là kết quả của một phiên bản chương trình và môi trường cụ thể. Khi những thành phần này thay đổi, cần đánh giá image có còn hợp lệ không.

### 13.1 Khi nào cần tạo checkpoint mới?

Thông thường nên tạo checkpoint mới khi:

- JAR hoặc application code thay đổi.
- Dependency Java thay đổi.
- JDK vendor/build hoặc CRaC runtime thay đổi.
- Checkpoint engine thay đổi.
- Base container image hoặc native library thay đổi.
- Environment variable ảnh hưởng trạng thái runtime thay đổi.
- Cấu hình khởi động hoặc JVM flags thay đổi.
- CPU architecture hoặc môi trường kernel thay đổi.
- Warm-up hoặc cache semantics thay đổi.

Một số thay đổi nhỏ có thể được vendor hỗ trợ trong một compatibility range nhất định. Tuy nhiên, không tự suy rộng phạm vi tương thích. Dùng ma trận hỗ trợ của đúng build và kiểm thử restore.

### 13.2 Checkpoint cũ và database schema mới

Checkpoint image có thể giữ code cũ trong khi database đã được migration. Trước restore, cần kiểm tra schema version có nằm trong compatibility range của application build hay không.

Nếu code cũ không tương thích schema mới, không restore image cũ. Dùng chiến lược expand/contract và quản lý tuổi thọ checkpoint artifact cùng deployment version.

### 13.3 Tag và retention

Có thể đặt naming convention:

~~~text
orders-service/
  2.8.1/
    linux-amd64/
      container-image-digest.txt
      checkpoint-001/
      checkpoint-002/
      manifest.json
  2.8.2/
    linux-amd64/
      ...
~~~

Không nhất thiết phải dùng cấu trúc thư mục này; điều quan trọng là mỗi checkpoint có ID riêng và liên kết tới build/runtime digest.

Đặt retention policy cho checkpoint cũ. Khi xóa image, cần bảo đảm không còn deployment hoặc rollback workflow nào tham chiếu tới nó.

## 14. Bảo mật artifact

JAR, container image và checkpoint image có các bề mặt bảo mật khác nhau.

| Artifact | Dữ liệu nhạy cảm có thể có | Cách bảo vệ |
|---|---|---|
| JAR | Code, endpoint, resource, đôi khi secret bị đóng gói nhầm | Scan artifact, không bake secret, ký và kiểm soát quyền tải |
| Container image | OS package, JDK, app binary, CA và config mặc định | Scan vulnerability, pin digest, ký image, chạy non-root |
| Checkpoint image | Heap, token, session, secret đã giải mã, dữ liệu người dùng, native memory | Mã hóa khi lưu/truyền, ACL chặt, audit access, retention và xóa an toàn |

Checkpoint image có thể chứa secret ngay cả khi ứng dụng lấy secret từ secret manager sau startup. Khi checkpoint, secret có thể đã được giải mã và nằm trong heap hoặc native memory.

Vì vậy:

- Không lưu checkpoint artifact trong bucket công khai.
- Giới hạn quyền đọc checkpoint theo environment và workload identity.
- Mã hóa artifact khi lưu và khi truyền.
- Không đưa secret vào manifest metadata.
- Kiểm soát việc copy checkpoint giữa development, staging và production.
- Xóa artifact hết hạn theo chính sách.
- Xem checkpoint image như một bản sao nhạy cảm của trạng thái ứng dụng.

Container image có thể được phân phối rộng hơn checkpoint artifact. Không nhất thiết mọi người có quyền pull container image đều được quyền tải checkpoint chứa dữ liệu runtime.

## 15. Reproducibility và build pipeline

Một pipeline tốt cần tạo ra các artifact có thể truy vết:

~~~mermaid
flowchart LR
    A["Git commit"] --> B["Build JAR"]
    B --> C["Test JAR"]
    C --> D["Build OCI image"]
    D --> E["Scan and sign image"]
    E --> F["Run CRaC warm-up job"]
    F --> G["Create checkpoint"]
    G --> H["Validate restore"]
    H --> I["Publish checkpoint + manifest"]
    I --> J["Deploy by immutable digest"]
~~~

Một số nguyên tắc:

- JAR nên được build từ source revision xác định.
- Container image nên pin base image và dependency.
- Checkpoint phải được tạo từ chính image đã ghi digest.
- Metadata phải liên kết checkpoint ID, JAR hash và container digest.
- Kiểm thử restore phải chạy bằng runtime/engine mục tiêu.
- Chỉ publish checkpoint sau khi restore test thành công theo tiêu chí pipeline.
- Giữ lại container image tương ứng trong suốt thời gian checkpoint còn được sử dụng.

Không nên tạo checkpoint từ một container đã được chỉnh sửa thủ công sau khi pull. Nếu filesystem thay đổi, digest ban đầu không còn mô tả chính xác môi trường đã tạo checkpoint.

## 16. Không đóng gói nhầm secret và cấu hình môi trường

Container image thường được build một lần rồi triển khai ở nhiều môi trường. Vì vậy, không nên bake credential, production endpoint hoặc dữ liệu riêng của một môi trường vào image.

Checkpoint lại có thể chứa trạng thái môi trường đã được nạp trong tiến trình. Nếu tạo image ở staging rồi restore trong production, heap có thể vẫn giữ:

- URL staging.
- Feature flags staging.
- Database endpoint staging.
- Credential staging.
- Tenant hoặc region ID staging.

Thay environment variable ở container mới không tự động thay các object đã được khôi phục trong heap. Ứng dụng cần reconcile các cấu hình phụ thuộc môi trường sau restore hoặc tạo checkpoint riêng cho từng environment.

Một checkpoint nên được gắn với environment hoặc config compatibility rõ ràng. Không chia sẻ image giữa môi trường chỉ vì JAR và container image giống nhau.

## 17. Các tình huống triển khai điển hình

### 17.1 Chỉ dùng JAR

Phù hợp khi chạy JVM trực tiếp hoặc môi trường không dùng container.

~~~text
JAR -> JVM startup -> Application
~~~

Ưu điểm là đơn giản và dễ di chuyển giữa các JDK tương thích. Nhược điểm là mỗi lần khởi động đều thực hiện startup và warm-up.

### 17.2 JAR trong container image, không dùng checkpoint

~~~text
JAR -> Container image -> New container -> New JVM
~~~

Phù hợp khi cần môi trường đóng gói nhất quán nhưng không cần giảm startup bằng CRaC.

### 17.3 JAR + container image + checkpoint artifact

~~~text
JAR -> CRaC container -> Warm-up -> Checkpoint artifact
                                         |
                                         v
                                Compatible container
                                         |
                                         v
                                      Restore
~~~

Phù hợp khi cần giảm thời gian khởi động nhiều instance và có thể kiểm soát môi trường restore.

### 17.4 Checkpoint riêng theo architecture

~~~text
Application JAR
    |
    +--> linux/amd64 container --> amd64 checkpoint
    |
    +--> linux/arm64 container --> arm64 checkpoint
~~~

Cách này phù hợp với cluster có nhiều kiến trúc CPU. Mỗi checkpoint cần metadata và validation riêng.

### 17.5 Checkpoint riêng theo environment

~~~text
Same application version
    |
    +--> staging runtime + staging config --> staging checkpoint
    |
    +--> production runtime + production config --> production checkpoint
~~~

Chỉ dùng chung checkpoint nếu đã xác minh cấu hình và trạng thái được phép dùng chung. Với credential, identity hoặc endpoint khác nhau, checkpoint riêng thường an toàn hơn.

## 18. Chẩn đoán khi restore không thành công

Khi restore lỗi, cần xác định lỗi thuộc lớp nào:

| Lớp | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Artifact | File thiếu, checksum sai, manifest không khớp | Kiểm tra checkpoint ID, hash, storage và quá trình publish |
| Container | Pull sai digest, thiếu file hoặc native library | Kiểm tra OCI digest, root filesystem và mount |
| Runtime | JDK/CRaC build không tương thích | Kiểm tra vendor, version, flags và engine |
| Platform | Kernel, architecture, CPU feature hoặc quyền khác | Kiểm tra host và cấu hình container runtime |
| Resource callback | beforeCheckpoint/afterRestore ném exception | Đọc exception và suppressed exception |
| External dependency | DB, DNS, secret hoặc service không sẵn sàng | Reconnect, validate và kiểm tra readiness |
| Application state | Cache, config hoặc schema cũ | Đối chiếu revision và compatibility |

Một số bước điều tra:

- Xác minh checkpoint artifact có đầy đủ các file mà engine yêu cầu.
- Kiểm tra checksum và metadata.
- Xác minh container digest đúng với image đã tạo checkpoint.
- Đọc log JVM, CRaC runtime và checkpoint engine.
- Xem exception tree của callback.
- Kiểm tra mount, permission, filesystem và file backing.
- Kiểm tra external service sau restore.
- Thử fresh startup từ cùng JAR để phân biệt lỗi ứng dụng với lỗi checkpoint.

Nếu fresh startup cũng lỗi, nguyên nhân có thể nằm ở JAR, container hoặc dependency. Nếu fresh startup thành công nhưng restore lỗi, hãy tập trung vào compatibility, process state và Resource lifecycle.

## 19. Checklist vận hành cho mỗi checkpoint release

Trước khi phát hành checkpoint artifact, cần ghi nhận:

- Application version và source revision.
- JAR checksum.
- Container image digest.
- JDK vendor/version/build.
- CRaC API/runtime version.
- Checkpoint engine/version.
- OS, kernel và CPU architecture.
- Các JVM flags liên quan.
- Config revision và environment.
- Database schema compatibility.
- Danh sách external resource đã được chuẩn bị.
- Checkpoint ID, timestamp và checksum.
- Kết quả restore test.
- Thời gian restore và readiness.
- Retention và quyền truy cập artifact.

Checklist này giúp đội vận hành biết chính xác checkpoint được tạo từ đâu và có thể dùng trong điều kiện nào. Nó cũng hỗ trợ rollback khi một build mới không thể restore.

## 20. Quy trình triển khai đề xuất

Một quy trình đóng gói Java CRaC có thể thực hiện theo các bước:

**Bước 1 — Build JAR.** Biên dịch code, đóng gói resource và dependency. Lưu source revision và checksum của JAR.

**Bước 2 — Build container image.** Chọn CRaC-enabled JDK runtime, copy JAR và native dependency cần thiết, pin base image digest và chạy non-root.

**Bước 3 — Khởi động trong môi trường mục tiêu.** Tạo container từ đúng image digest, nạp cấu hình và kiểm tra dependency.

**Bước 4 — Warm-up.** Chạy các bước khởi tạo cần thiết, đưa ứng dụng tới trạng thái checkpoint-ready và không nhận traffic nếu quy trình yêu cầu.

**Bước 5 — Tạo checkpoint.** CRaC gọi beforeCheckpoint, checkpoint engine ghi process image và pipeline thu thập metadata.

**Bước 6 — Liên kết artifact.** Lưu checkpoint với JAR hash, container digest, JDK build, engine, OS và architecture. Dùng ID bất biến.

**Bước 7 — Kiểm thử restore.** Tạo container tương thích, restore image, chạy afterRestore và xác minh external dependencies.

**Bước 8 — Publish.** Chỉ publish checkpoint đã qua kiểm tra restore và bảo mật. Giữ container image tương ứng trong registry.

**Bước 9 — Deploy.** Chọn checkpoint theo metadata, xác minh tương thích và restore. Nếu không thể restore, dùng fresh startup từ JAR theo fallback policy.

**Bước 10 — Theo dõi và thu hồi.** Đo startup/restore time, readiness, lỗi callback và quản lý retention của checkpoint cũ.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và vai trò phối hợp với ứng dụng Java.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): chuẩn bị runtime và chạy ứng dụng CRaC.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): các checkpoint engine và khác biệt theo build.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): Resource callback và lifecycle của ứng dụng.
- [Open Container Initiative — Image Format Specification](https://github.com/opencontainers/image-spec): cấu trúc và metadata của container image.
- [Open Container Initiative — Distribution Specification](https://github.com/opencontainers/distribution-spec): phân phối artifact qua registry.
- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/): tách build stage và runtime stage.
- [Docker — Image digests](https://docs.docker.com/dhi/core-concepts/digests/): định danh bất biến của image.
- [Java JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html): cấu trúc JAR và manifest.
- [Kubernetes — Container Images](https://kubernetes.io/docs/concepts/containers/images/): sử dụng image, tag và digest trong deployment.

