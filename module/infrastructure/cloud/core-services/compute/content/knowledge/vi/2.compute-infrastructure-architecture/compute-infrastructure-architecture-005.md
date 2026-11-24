# Kiến trúc x86 và Arm: tính tương thích của ứng dụng và thư viện

Khi chọn máy chủ cloud, đội ngũ thường chú ý đến số vCPU, bộ nhớ, băng thông mạng và giá mỗi giờ. Một quyết định khác có thể ảnh hưởng sâu đến khả năng triển khai ứng dụng là **kiến trúc tập lệnh của CPU**. Hai nền tảng phổ biến trong hạ tầng cloud là x86-64 và Arm64. Chúng đều có thể chạy hệ điều hành Linux 64-bit và phục vụ nhiều loại workload, nhưng không dùng cùng tập lệnh máy. Vì vậy, một chương trình đã biên dịch cho x86-64 thường không thể chạy trực tiếp trên máy Arm64 nếu không có bản dựng tương thích hoặc lớp chuyển đổi phù hợp.

Bài học này thuộc chương **Kiến trúc hạ tầng tính toán** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong bối cảnh đó, hiểu x86 và Arm giúp chọn đúng loại compute, đóng gói phần mềm đúng kiến trúc và chuyển đổi workload mà không làm gián đoạn dịch vụ.

## 1. Kiến trúc CPU và tập lệnh

### 1.1. ISA là gì?

**Instruction Set Architecture (ISA)**, hay kiến trúc tập lệnh, là giao diện mà phần mềm đã biên dịch sử dụng để yêu cầu CPU thực hiện thao tác. ISA quy định các loại lệnh, thanh ghi, cách truy cập bộ nhớ, mô hình ngoại lệ và một số hành vi nền tảng khác.

Compiler dịch mã nguồn thành mã máy phù hợp với một ISA và một môi trường thực thi cụ thể. CPU chỉ thực thi trực tiếp các lệnh mà nó hỗ trợ. Vì vậy, một binary được tạo cho ISA này không mặc nhiên chạy được trên CPU dùng ISA khác.

Cần phân biệt ba lớp:

- **Kiến trúc tập lệnh (ISA):** quy định tập lệnh và trạng thái máy mà phần mềm nhìn thấy.
- **Vi kiến trúc (microarchitecture):** cách một dòng CPU hiện thực ISA bằng pipeline, cache, bộ dự đoán nhánh, đơn vị thực thi và các cơ chế nội bộ.
- **ABI (Application Binary Interface):** quy ước ở mức nhị phân để chương trình, thư viện và hệ điều hành tương tác, chẳng hạn cách truyền tham số, trả kết quả, gọi hàm và bố trí dữ liệu.

Hai CPU có thể thực thi cùng ISA nhưng có vi kiến trúc, số lõi, xung nhịp, cache và hiệu năng khác nhau. Ngược lại, hai CPU có ISA khác nhau vẫn có thể chạy cùng một ứng dụng nếu ứng dụng được biên dịch hoặc đóng gói riêng cho từng nền tảng.

### 1.2. x86-64 và Arm64

| Đặc điểm | x86-64 | Arm64 |
|---|---|---|
| Tên thường gặp | AMD64, x86_64, Intel 64 | AArch64, ARM64 |
| Nhà phát triển ISA | Hệ sinh thái x86 do Intel và AMD phát triển | Arm thiết kế ISA và cấp phép cho nhiều nhà sản xuất CPU |
| Mô hình tập lệnh | Thường được mô tả là CISC, có nhiều dạng mã lệnh và độ dài lệnh khác nhau | Thường được mô tả là RISC, có hệ lệnh mã hóa tương đối đều đặn |
| Thanh ghi và ABI | Có quy ước riêng theo nền tảng, hệ điều hành và ABI | Có quy ước AArch64 riêng theo hệ điều hành và ABI |
| Binary | Binary x86-64 | Binary AArch64/Arm64 |
| Hệ điều hành | Linux, Windows và các hệ điều hành hỗ trợ x86-64 | Linux, Windows và các hệ điều hành hỗ trợ Arm64 |

CISC và RISC là cách mô tả lịch sử về triết lý ISA. CPU hiện đại có nhiều kỹ thuật nội bộ phức tạp, vì vậy không nên suy ra rằng mọi CPU Arm đều đơn giản hơn hoặc luôn tiết kiệm điện hơn mọi CPU x86. Kết quả phụ thuộc vào thế hệ CPU, thiết kế máy chủ, workload, cấu hình bộ nhớ, hệ thống làm mát và cách phần mềm được tối ưu.

Trong môi trường cloud, tên kiến trúc thường xuất hiện dưới các dạng sau:

| Môi trường hoặc công cụ | x86-64 | Arm64 |
|---|---|---|
| Linux **uname -m** | **x86_64** | **aarch64** |
| Debian/Ubuntu package architecture | **amd64** | **arm64** |
| Docker/OCI platform | **linux/amd64** | **linux/arm64** |
| Kubernetes node label | **kubernetes.io/arch=amd64** | **kubernetes.io/arch=arm64** |

Các tên trên cùng chỉ một họ kiến trúc ở những lớp khác nhau. Khi đọc log build, manifest container hoặc metadata máy chủ, cần dùng đúng cách ghi mà công cụ đó yêu cầu.

### 1.3. Kiến trúc CPU không phải là hệ điều hành

Một máy Linux Arm64 và một máy Linux x86-64 có thể cung cấp giao diện lập trình tương tự ở cấp ứng dụng, nhưng binary native của chúng khác nhau. Tương tự, việc hai máy cùng chạy Linux không có nghĩa một file thực thi biên dịch cho máy này sẽ chạy trên máy kia.

Ngoài ISA, khả năng tương thích còn phụ thuộc:

- Hệ điều hành và phiên bản kernel.
- ABI và dynamic loader.
- Thư viện hệ thống như glibc hoặc musl.
- Runtime của ngôn ngữ lập trình.
- Thư viện native, plugin và driver.
- Các tính năng CPU mà chương trình yêu cầu, chẳng hạn AVX trên một số CPU x86 hoặc các phần mở rộng SIMD trên Arm.

Do đó, cần đánh giá cả nền tảng thực thi thay vì chỉ kiểm tra tên CPU.

## 2. Những lớp tương thích của ứng dụng

### 2.1. Mã nguồn và binary

Mã nguồn C, C++, Rust hoặc Go có thể được viết theo cách độc lập kiến trúc. Tuy nhiên, compiler vẫn phải tạo binary phù hợp với nền tảng đích. Một dự án có mã nguồn dùng được trên cả hai kiến trúc thường cần build hai artifact riêng.

Ví dụ, chương trình Go thuần có thể cross-compile cho Linux AMD64 và ARM64:

~~~bash
GOOS=linux GOARCH=amd64 go build -o app-linux-amd64 ./cmd/app
GOOS=linux GOARCH=arm64 go build -o app-linux-arm64 ./cmd/app
~~~

Cross-compile nghĩa là compiler chạy trên một máy nhưng tạo binary cho nền tảng đích khác. Quy trình này hữu ích cho CI/CD, song không thay thế kiểm thử trên máy đích. Nếu ứng dụng dùng CGO, thư viện C hoặc toolchain native, cần có cross-compiler và các thư viện phát triển phù hợp. Không thể tùy tiện tắt CGO nếu chương trình phụ thuộc vào nó.

Một chương trình đã biên dịch thường chứa mã máy và metadata theo định dạng của hệ điều hành. Trên Linux, binary native thường dùng định dạng ELF. Một file ELF x86-64 không trở thành ELF Arm64 chỉ bằng cách đổi tên file hoặc sao chép sang máy khác.

### 2.2. ABI và thư viện native

**ABI** quy định cách các thành phần nhị phân tương tác. Các yếu tố quan trọng gồm:

- Quy ước gọi hàm (calling convention): tham số được truyền qua thanh ghi hay stack, cách trả kết quả và cách bảo toàn thanh ghi.
- Kích thước và cách căn chỉnh dữ liệu.
- Cách xử lý ngoại lệ và symbol.
- Giao diện gọi hệ thống (system call interface).
- Quy tắc liên kết thư viện tĩnh hoặc động.

Thư viện native thường được biên dịch cho một tổ hợp cụ thể của kiến trúc, hệ điều hành và ABI. Ví dụ, một ứng dụng Python có thể chạy trên cả x86-64 và Arm64, nhưng một package Python có extension viết bằng C/C++ cần wheel tương ứng với nền tảng đích hoặc phải được build từ mã nguồn.

Các phụ thuộc thường gây trở ngại khi chuyển kiến trúc:

- Module Python có extension native.
- Package Node.js chứa addon native hoặc tải binary dựng sẵn.
- Thư viện C/C++ được liên kết với glibc, musl hoặc phiên bản runtime cụ thể.
- Plugin database, driver, codec, thư viện xử lý ảnh và thư viện mật mã.
- Agent giám sát, antivirus, profiler hoặc thành phần bảo mật có module kernel.
- Công cụ thương mại chỉ phát hành binary cho một số kiến trúc.

Không nên chỉ kiểm tra dependency trực tiếp. Cần rà soát cả dependency bắc cầu, plugin được nạp lúc chạy và các binary được tải động.

### 2.3. Runtime của ngôn ngữ lập trình

Một số ngôn ngữ có khả năng che giấu khác biệt kiến trúc tốt hơn vì mã được thực thi thông qua runtime:

| Nền tảng | Hành vi khi chuyển x86-64 sang Arm64 |
|---|---|
| Java/JVM | Bytecode thường dùng được trên cả hai kiến trúc nếu có JVM tương thích; thư viện JNI vẫn cần binary native đúng kiến trúc. |
| .NET | IL thường dùng được trên runtime hỗ trợ nền tảng đích; native dependency và thư viện P/Invoke phải tương thích. |
| Python | Mã Python thuần thường dùng được; extension C/C++ và wheel phải hỗ trợ Arm64. |
| Node.js | JavaScript thuần thường dùng được; native addon và package có binary dựng sẵn cần phiên bản Arm64. |
| Go | Có thể build cho nhiều kiến trúc; thư viện dùng CGO hoặc assembly riêng cần được xử lý tương ứng. |
| Rust | Có thể compile cho nhiều target; crate gọi thư viện native hoặc dùng intrinsic đặc thù cần kiểm tra. |
| C/C++ | Cần build lại cho kiến trúc đích và xử lý các thư viện native, assembly hoặc compiler intrinsic phụ thuộc CPU. |

Runtime cũng phải có bản phát hành cho hệ điều hành và kiến trúc tương ứng. Một file JAR độc lập có thể chạy trên JVM Arm64, nhưng nếu ứng dụng phụ thuộc thư viện JNI chỉ có bản x86-64 thì ứng dụng vẫn không tương thích hoàn toàn.

## 3. Tương thích của container và image

### 3.1. Container không loại bỏ khác biệt ISA

Container chia sẻ kernel của host và đóng gói ứng dụng cùng các thư viện phụ thuộc. Container image không phải một máy ảo có CPU riêng. Vì vậy, image chứa binary x86-64 thường cần host x86-64; image chứa binary Arm64 cần host Arm64, trừ khi có lớp emulation hoặc chuyển đổi nhị phân.

Một image có thể chỉ hỗ trợ một kiến trúc hoặc cung cấp nhiều biến thể. Với chuẩn OCI, một image index (thường được gọi là manifest list) có thể trỏ đến nhiều image manifest riêng, mỗi manifest dành cho một nền tảng. Container runtime chọn biến thể phù hợp với host khi pull image.

~~~mermaid
flowchart TB
    P["Tên image: registry.example.com/api:1.0"]
    I["OCI image index / manifest list"]
    X["Manifest linux/amd64"]
    A["Manifest linux/arm64"]
    X1["Layers và binary x86-64"]
    A1["Layers và binary Arm64"]
    P --> I
    I --> X
    I --> A
    X --> X1
    A --> A1
~~~

Một tag image có thể đại diện cho nhiều kiến trúc, nhưng điều đó chỉ đúng khi registry đã lưu manifest đa nền tảng. Đổi tag hoặc copy một image đơn kiến trúc sang registry khác không tự tạo ra biến thể còn thiếu.

### 3.2. Build image đa kiến trúc

Docker Buildx có thể tạo image cho nhiều platform trong cùng một lần build:

~~~bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/team/api:1.0.0 \
  --push .
~~~

Lệnh này yêu cầu builder hỗ trợ các platform đích và registry nhận image được push. Builder có thể dùng máy build native cho từng kiến trúc hoặc dùng QEMU để giả lập trong một số bước. Build qua giả lập thường chậm hơn và vẫn cần kiểm thử trên phần cứng hoặc môi trường native.

Một Dockerfile có thể dùng biến **TARGETARCH** để chọn gói hoặc binary đúng kiến trúc. Ví dụ sau chỉ minh họa cách truyền platform vào build; đường dẫn tải và checksum phải được thay bằng nguồn artifact thực tế đã kiểm chứng.

~~~dockerfile
# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM golang:1.24 AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY . .
RUN GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o /out/api ./cmd/api

FROM debian:bookworm-slim
COPY --from=build /out/api /usr/local/bin/api
ENTRYPOINT ["/usr/local/bin/api"]
~~~

Trong ví dụ, stage build chạy trên platform của builder, còn **TARGETOS** và **TARGETARCH** chỉ định nền tảng cần tạo binary. Cách làm này phù hợp với dự án Go không phụ thuộc CGO hoặc đã cấu hình toolchain cross-compile đầy đủ. Với C/C++, CGO hoặc dependency native phức tạp, cần bổ sung cross-toolchain và thư viện cho target.

Sau khi push, nên kiểm tra manifest:

~~~bash
docker buildx imagetools inspect registry.example.com/team/api:1.0.0
~~~

Kết quả cần thể hiện các platform mong muốn, ví dụ **linux/amd64** và **linux/arm64**. Đồng thời phải pull và chạy thử trên node của từng kiến trúc.

### 3.3. Base image và package manager

Base image cũng phải hỗ trợ kiến trúc đích. Một tag phổ biến có thể hỗ trợ đa kiến trúc, nhưng không phải mọi tag, biến thể hoặc package trong repository đều có sẵn cho Arm64.

Cần kiểm tra:

- Image nền có manifest cho platform cần triển khai hay không.
- Repository hệ điều hành có package đúng kiến trúc và phiên bản hay không.
- Binary được tải trong Dockerfile có đúng architecture không.
- Script cài đặt có tự chọn package theo **uname -m** hoặc metadata platform đúng cách không.
- File native được copy từ stage build có thực sự là binary cho target hay không.

Không nên dựa vào việc image build thành công để kết luận image chạy đúng. Một số lỗi chỉ xuất hiện khi container khởi động, tải dynamic library hoặc thực hiện nhánh code dùng instruction đặc thù.

## 4. Khả năng tương thích trong Kubernetes và cloud

### 4.1. Cluster có node x86-64 và Arm64

Một Kubernetes cluster có thể gồm node thuộc nhiều kiến trúc. Node thường công bố label chuẩn **kubernetes.io/arch**. Scheduler dùng các label và ràng buộc pod để đặt workload lên node phù hợp.

Ví dụ, workload sau chỉ được lập lịch lên node Arm64:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-arm64
spec:
  replicas: 2
  selector:
    matchLabels:
      app: api-arm64
  template:
    metadata:
      labels:
        app: api-arm64
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: kubernetes.io/arch
                    operator: In
                    values:
                      - arm64
      containers:
        - name: api
          image: registry.example.com/team/api:1.0.0
          ports:
            - containerPort: 8080
~~~

Nếu image **api:1.0.0** có manifest đa kiến trúc, runtime có thể lấy biến thể Arm64 khi pod chạy trên node Arm64. Nếu image chỉ có biến thể AMD64, pod có thể gặp lỗi khởi động như **exec format error**.

Có thể quan sát kiến trúc node bằng lệnh:

~~~bash
kubectl get nodes -L kubernetes.io/arch
~~~

Với cluster hỗn hợp, cần quyết định workload nào được phép chạy ở cả hai kiến trúc. Có thể dùng node affinity để giới hạn kiến trúc, taint/toleration để cô lập node pool, hoặc để scheduler tự chọn node nếu image và workload đã hỗ trợ đa kiến trúc.

### 4.2. Dịch vụ compute managed và serverless

Với máy ảo, kiến trúc thường được thể hiện trong tên họ instance hoặc thuộc tính cấu hình. Khi tạo máy, cần xác nhận image hệ điều hành, agent, driver và ứng dụng đều hỗ trợ kiến trúc CPU đã chọn.

Với dịch vụ container managed hoặc Kubernetes managed, cần kiểm tra kiến trúc của node pool, control plane, image và add-on. Một số thành phần do nhà cung cấp quản lý có thể có giới hạn kiến trúc riêng.

Với serverless, nhà cung cấp có thể cho chọn kiến trúc runtime hoặc tự quản lý phần cứng bên dưới. Dù không quản lý host, ứng dụng vẫn cần tương thích với runtime, package native, layer và extension được triển khai. Kiểm tra danh sách runtime, region, kiến trúc và giới hạn của dịch vụ trước khi chuyển workload.

Không nên suy luận rằng một dịch vụ managed hỗ trợ Arm chỉ vì dịch vụ đó chạy container hoặc Linux. Phạm vi hỗ trợ có thể khác giữa loại compute, phiên bản runtime, region và tính năng.

### 4.3. Hệ sinh thái vận hành

Ngoài ứng dụng, các công cụ vận hành cũng cần hỗ trợ kiến trúc:

- Monitoring agent và log collector.
- Security scanner, endpoint agent và runtime protection.
- Backup agent, storage driver và CSI plugin.
- APM profiler, tracing agent và eBPF tool.
- Database extension, plugin và migration utility.
- CI runner, build agent và công cụ ký artifact.

Một workload có thể khởi động thành công nhưng thiếu agent bảo mật hoặc monitoring trên Arm64. Trước khi chuyển môi trường production, cần xác nhận toàn bộ chuỗi vận hành có bản tương thích và được nhà cung cấp hỗ trợ.

## 5. Những nguyên nhân gây lỗi khi chuyển kiến trúc

### 5.1. Phụ thuộc binary được đóng gói sẵn

Một installer có thể tải file binary dựa trên tên hệ điều hành mà không kiểm tra kiến trúc. Khi chạy trên Arm64, script vẫn tải bản x86-64 và lỗi ở bước thực thi.

Cách xử lý là kiểm tra kiến trúc trước khi tải, chọn artifact tương ứng và xác minh checksum hoặc chữ ký. Với dependency quan trọng, ưu tiên package chính thức có hỗ trợ kiến trúc đích.

### 5.2. Assembly và intrinsic đặc thù

Một số thư viện tối ưu bằng assembly hoặc intrinsic riêng cho x86, chẳng hạn mã dùng các phần mở rộng SIMD như AVX. Phần mã đó không thể chạy trực tiếp trên Arm64. Thư viện cần có implementation thay thế hoặc đường code portable.

Tương tự, Arm có các phần mở rộng SIMD như NEON và các tính năng tùy CPU. Không phải mọi CPU Arm đều hỗ trợ cùng một tập phần mở rộng. Chương trình nên kiểm tra feature phù hợp hoặc dùng thư viện tự chọn implementation an toàn.

### 5.3. Giả định về bộ nhớ và đồng thời

Mô hình bộ nhớ của CPU ảnh hưởng đến cách các thao tác load/store được quan sát giữa nhiều lõi. x86-64 và Arm64 có các đặc điểm memory ordering khác nhau. Code đồng thời dựa vào giả định quá mạnh về thứ tự truy cập bộ nhớ có thể hoạt động trên một nền tảng nhưng bộc lộ race condition trên nền tảng khác.

Cần dùng primitive đồng bộ đúng của ngôn ngữ và thư viện: mutex, atomic, channel hoặc memory barrier theo quy định của runtime. Không nên dùng thao tác đọc/ghi thông thường thay cho cơ chế đồng bộ chỉ vì kiểm thử trên một loại CPU chưa phát hiện lỗi.

### 5.4. Căn chỉnh, kích thước và biểu diễn dữ liệu

Các giả định về alignment, kích thước kiểu dữ liệu, layout struct, bit field hoặc thứ tự byte có thể gây lỗi khi chuyển nền tảng. x86-64 và Arm64 trong hạ tầng cloud hiện đại thường dùng little-endian, nhưng định dạng dữ liệu bền vững và giao thức mạng vẫn nên quy định rõ byte order, kích thước trường và cách serialize.

Tránh ghi trực tiếp cấu trúc nội bộ của chương trình xuống file hoặc gửi qua mạng như một định dạng không phiên bản. Dùng định dạng serialization có schema hoặc giao thức quy định rõ biểu diễn dữ liệu.

### 5.5. Kernel module và driver

Kernel module thường gắn chặt với kiến trúc, phiên bản kernel và cách build. Driver hoặc agent chỉ phát hành cho x86-64 có thể không cài được trên Arm64. Với workload cần GPU, thiết bị tăng tốc, thiết bị mạng đặc biệt hoặc storage driver, cần xác minh cả phần cứng lẫn stack driver.

### 5.6. Giới hạn của dependency và giấy phép

Một thư viện có thể có source code nhưng giấy phép thương mại chỉ cho phép chạy trên một số nền tảng hoặc một số loại CPU. Nhà cung cấp phần mềm có thể chưa chứng nhận Arm64 dù chương trình có thể build về mặt kỹ thuật. Với hệ thống doanh nghiệp, cần xác nhận hỗ trợ chính thức, điều khoản license và chính sách hỗ trợ trước khi chuyển đổi.

## 6. Chiến lược chuyển workload từ x86-64 sang Arm64

Không nên thay đổi kiến trúc đồng loạt trước khi hiểu dependency và hành vi workload. Một quy trình có kiểm soát gồm các bước sau.

### Bước 1: Lập danh mục workload và dependency

Với từng ứng dụng, ghi nhận:

- Ngôn ngữ, runtime và phiên bản compiler.
- Hệ điều hành, base image và kiến trúc hiện tại.
- Binary native, package, plugin, extension và driver.
- Thư viện bên ngoài, dịch vụ managed và agent vận hành.
- Yêu cầu CPU, bộ nhớ, I/O, mạng và thiết bị tăng tốc.
- Mức quan trọng, SLO, cửa sổ bảo trì và phương án rollback.

Phân loại mỗi thành phần thành: đã hỗ trợ Arm64; có thể build lại; cần nâng cấp hoặc thay thế; chưa có phương án tương thích. Dependency chưa xác định được phải được xem là rủi ro cần giải quyết trước khi chuyển production.

### Bước 2: Xác nhận nền tảng đích

Chọn dòng máy Arm64 có đủ CPU, bộ nhớ, mạng, lưu trữ và tính năng cần thiết. Kiểm tra region, quota, loại image, hệ điều hành, kernel, runtime, agent và driver.

Đọc ma trận hỗ trợ của nhà cung cấp phần mềm. Nếu dùng database, middleware hoặc sản phẩm thương mại, xác nhận phiên bản và kiến trúc được chứng nhận.

### Bước 3: Build lại artifact

Tạo binary, package và container image riêng cho từng kiến trúc. Gắn metadata rõ ràng vào artifact và tag. Với container, ưu tiên manifest đa kiến trúc để cùng một tag có thể được pull đúng biến thể theo node.

Build phải tái lập được: cố định phiên bản compiler, dependency, base image và checksum; lưu log build và kết quả kiểm tra artifact. Tránh dùng binary được copy thủ công từ máy phát triển mà không biết kiến trúc.

### Bước 4: Kiểm thử chức năng và tích hợp

Chạy unit test, integration test, kiểm thử database, queue, cache, xác thực, mã hóa và các đường xử lý lỗi trên Arm64. Kiểm tra những nhánh sử dụng thư viện native, concurrency, SIMD hoặc plugin.

Kiểm thử cả quy trình triển khai và vận hành: khởi động, health check, autoscaling, logging, monitoring, backup, restore, cập nhật và rollback. Một ứng dụng trả HTTP 200 chưa đủ chứng minh toàn bộ hệ thống tương thích.

### Bước 5: Benchmark bằng tải đại diện

Đo trên loại máy đích bằng dữ liệu và mẫu tải gần với production. Theo dõi throughput, latency p50/p95/p99, CPU utilization, memory, garbage collection, network, storage IOPS và chi phí theo đơn vị công việc.

Không so sánh chỉ bằng số vCPU hoặc xung nhịp. Hai máy có cùng số vCPU nhưng khác thế hệ CPU, cache, memory bandwidth và cấu hình có thể cho kết quả khác nhau. Nên đo chi phí cho mỗi request, mỗi job hoặc mỗi giao dịch thành công.

### Bước 6: Canary và mở rộng dần

Chuyển một nhóm workload nhỏ sang Arm64, giữ lại khả năng phục vụ trên x86-64. Dùng traffic splitting, hàng đợi hoặc nhóm worker riêng để giới hạn blast radius. Theo dõi lỗi, latency, throughput và chi phí trước khi tăng tỷ lệ.

Đặt ngưỡng rollback rõ ràng. Nếu tỷ lệ lỗi, latency hoặc sai lệch dữ liệu vượt ngưỡng, chuyển traffic về nền tảng cũ và điều tra. Chỉ mở rộng sau khi đã chứng minh workload ổn định qua chu kỳ tải đại diện.

### Bước 7: Dọn dẹp và chuẩn hóa

Khi chuyển đổi đạt yêu cầu, cập nhật tài liệu kiến trúc, IaC, pipeline, danh mục image, hướng dẫn vận hành và kế hoạch capacity. Giữ lại binary hoặc môi trường x86-64 trong thời gian rollback cần thiết, sau đó mới loại bỏ phần tài nguyên không còn dùng.

## 7. Kiểm thử và tự động hóa đa kiến trúc

### 7.1. CI/CD matrix

Pipeline nên build và test cho từng target một cách tường minh. Ví dụ, một pipeline có thể tạo hai job:

~~~yaml
strategy:
  matrix:
    include:
      - platform: linux/amd64
        arch: amd64
      - platform: linux/arm64
        arch: arm64
steps:
  - name: Build and test
    run: |
      docker buildx build \
        --platform ${{ matrix.platform }} \
        --tag registry.example.com/team/api:${{ matrix.arch }} \
        --load .
      docker run --rm registry.example.com/team/api:${{ matrix.arch }} ./api --version
~~~

Đây là ví dụ minh họa cú pháp matrix của một hệ thống CI kiểu GitHub Actions. Cấu hình thực tế cần bổ sung bước checkout, thiết lập Buildx, đăng nhập registry, runner tương thích và lệnh test của dự án. **--load** thường nạp image vào local Docker engine của builder; khả năng load nhiều platform phụ thuộc builder và môi trường. Có thể build riêng từng platform rồi push, hoặc build manifest đa kiến trúc ở bước phát hành.

Nên chạy test native trên runner x86-64 và Arm64 khi có thể. Cross-compile giúp tạo artifact nhưng không xác nhận binary hoạt động đúng trên phần cứng đích. QEMU hữu ích để kiểm tra nhanh hoặc hỗ trợ build, song benchmark và xác nhận production nên dùng môi trường native.

### 7.2. Kiểm tra metadata artifact

Trước khi phát hành, kiểm tra:

- Kiến trúc và hệ điều hành mục tiêu của binary.
- Các thư viện động mà binary cần.
- Image manifest có đủ platform.
- Phiên bản base image và package.
- Chữ ký, checksum và provenance của artifact.
- SBOM có ghi nhận dependency native.
- Vulnerability scan được thực hiện trên từng biến thể.

Không nên giả định hai image variant có nội dung giống hệt nhau. Một dependency có thể khác phiên bản hoặc bị thiếu trên một kiến trúc. Vì vậy, kiểm thử và quét bảo mật phải áp dụng cho từng biến thể.

### 7.3. Quan sát production

Tách chỉ số theo kiến trúc hoặc node pool để nhận ra khác biệt. Các nhãn như **arch=amd64** và **arch=arm64** có thể được đưa vào metric, log hoặc dashboard. Cần tránh gắn quá nhiều nhãn có cardinality cao vào telemetry.

Theo dõi ít nhất:

- Tỷ lệ lỗi và restart của pod theo kiến trúc.
- Latency và throughput theo phiên bản ứng dụng.
- CPU throttling, memory pressure và OOM kill.
- Thời gian khởi động, autoscaling và thời gian xử lý job.
- Lỗi tải thư viện, **exec format error** và lỗi native extension.
- Chi phí compute theo workload hoặc đơn vị nghiệp vụ.

## 8. Chọn x86-64 hay Arm64 cho workload cloud

Không có kiến trúc nào luôn tốt hơn trong mọi tình huống. Lựa chọn phụ thuộc vào tính tương thích, hiệu năng đo được, chi phí, khả năng vận hành và hỗ trợ của nhà cung cấp.

| Tiêu chí | x86-64 thường phù hợp khi | Arm64 thường phù hợp khi |
|---|---|---|
| Tương thích phần mềm | Có dependency thương mại, driver hoặc binary legacy chỉ hỗ trợ x86-64 | Ứng dụng và dependency đã hỗ trợ Arm64 hoặc có thể build lại |
| Hệ sinh thái | Cần hỗ trợ rộng từ công cụ, agent và phần mềm lâu năm | Stack đã xác nhận có bản native và quy trình build/test đa kiến trúc |
| Hiệu năng | Workload đã tối ưu cho x86 hoặc cần instruction extension cụ thể | Workload chạy tốt trên CPU Arm và đạt mục tiêu hiệu năng qua benchmark |
| Chi phí | Giá và hiệu năng của dòng máy x86 đáp ứng tốt yêu cầu | Dòng máy Arm có tổng chi phí cho mỗi đơn vị công việc tốt hơn trong phép đo thực tế |
| Di chuyển | Muốn giữ nguyên binary và hạn chế thay đổi nền tảng | Có thể đầu tư build, kiểm thử và rollout có kiểm soát |
| Hỗ trợ | Nhà cung cấp ứng dụng chỉ chứng nhận x86-64 | Nhà cung cấp xác nhận Arm64 hoặc workload được đội ngũ tự hỗ trợ đầy đủ |

### 8.1. Workload có thể phù hợp với Arm64

Các workload có mã nguồn và dependency hỗ trợ đa kiến trúc thường dễ chuyển đổi hơn, ví dụ:

- API stateless chạy trên runtime phổ biến có bản Arm64.
- Web service và worker được build từ source.
- Batch processing có thể benchmark và chạy song song.
- Microservice container có image đa kiến trúc.
- Một số workload scale-out, nơi chi phí mỗi request hoặc mỗi job là chỉ số quan trọng.

Đây chỉ là nhóm ứng viên để đánh giá. Không nên kết luận một workload phù hợp chỉ vì nó chạy Linux hoặc dùng container.

### 8.2. Workload nên giữ x86-64 cho đến khi có phương án rõ ràng

Cân nhắc giữ x86-64 nếu hệ thống phụ thuộc vào:

- Binary độc quyền không có bản Arm64.
- Kernel module, driver hoặc thiết bị chỉ hỗ trợ x86.
- Phần mềm thương mại chưa chứng nhận Arm64.
- Thư viện tối ưu đặc thù chưa có implementation Arm.
- Công cụ vận hành hoặc agent bắt buộc chưa hỗ trợ nền tảng mới.
- Workload nhạy với độ trễ hoặc tính năng CPU nhưng chưa có kết quả benchmark đáng tin cậy.

Giữ x86-64 là quyết định hợp lý khi chi phí chuyển đổi và rủi ro vận hành lớn hơn lợi ích đã đo được.

## 9. Ví dụ thực tế

### Ví dụ A: API Go chạy trên hai kiến trúc

Một API Go dùng thư viện thuần Go có thể được build thành hai binary:

~~~bash
GOOS=linux GOARCH=amd64 go build -o api-amd64 ./cmd/api
GOOS=linux GOARCH=arm64 go build -o api-arm64 ./cmd/api
~~~

CI chạy unit test và integration test trên runner tương ứng. Pipeline đóng gói hai binary vào image variant riêng, sau đó phát hành một tag đa kiến trúc. Khi pod chạy trên node AMD64 hoặc Arm64, runtime lấy đúng biến thể.

Nếu ứng dụng dùng CGO hoặc thư viện native, nhóm cần bổ sung cross-toolchain, package hệ thống và test trên từng kiến trúc.

### Ví dụ B: Dịch vụ Python có package native

Một dịch vụ Python dùng thư viện xử lý ảnh. Phần mã Python có thể dùng chung, nhưng package xử lý ảnh có extension native. Nhóm kiểm tra wheel cho phiên bản Python, hệ điều hành, libc và kiến trúc đích.

Nếu wheel Arm64 có sẵn, build image Arm64 và chạy test chức năng. Nếu không có wheel nhưng có source, nhóm đánh giá khả năng build từ source và dependency C/C++. Nếu thư viện không thể build hoặc nhà cung cấp không hỗ trợ, workload tiếp tục chạy trên x86-64 cho đến khi có giải pháp được xác nhận.

### Ví dụ C: Kubernetes cluster hỗn hợp

Một cluster có node pool x86-64 và Arm64. Các microservice đã phát hành image đa kiến trúc có thể chạy trên cả hai node pool. Một workload cũ chỉ có binary AMD64 được gắn node affinity vào pool x86-64.

Đội vận hành theo dõi chi phí và hiệu năng theo node pool. Sau khi dependency được nâng cấp và image Arm64 vượt qua kiểm thử, workload cũ được chuyển dần bằng canary. Cluster hỗn hợp giúp di chuyển theo từng dịch vụ thay vì phải thay đổi toàn bộ hệ thống cùng lúc.

## 10. Những sai lầm thường gặp

**Cho rằng container image chạy trên mọi CPU.** Container đóng gói user space nhưng vẫn phụ thuộc kiến trúc của binary và kernel host. Cần có image variant đúng platform hoặc lớp chuyển đổi phù hợp.

**Chỉ kiểm tra mã nguồn mà quên dependency.** Source code có thể portable trong khi extension, plugin, driver hoặc binary tải lúc chạy chỉ hỗ trợ x86-64. Cần kiểm kê dependency đến cả thành phần bắc cầu.

**Dùng cross-compile làm bằng chứng tương thích.** Build thành công không chứng minh binary chạy đúng, thư viện tải được hoặc workload đạt hiệu năng. Cần test trên môi trường native của kiến trúc đích.

**Dùng QEMU để kết luận hiệu năng production.** Emulation hữu ích cho một số tác vụ build và test nhưng hiệu năng không đại diện cho CPU native. Benchmark cần chạy trên instance thực tế.

**So sánh chỉ bằng số vCPU hoặc giá giờ.** Hiệu năng phụ thuộc nhiều yếu tố. Hãy đo latency, throughput và chi phí cho một đơn vị công việc dưới tải đại diện.

**Quên agent và công cụ vận hành.** Ứng dụng chạy được nhưng monitoring, backup hoặc security agent không hoạt động vẫn khiến hệ thống chưa sẵn sàng production.

**Chuyển toàn bộ workload trong một lần.** Thay đổi lớn làm tăng blast radius và khó xác định nguyên nhân nếu có lỗi. Nên bắt đầu bằng workload ít rủi ro, canary và có rollback.

**Dùng chung tag nhưng không kiểm tra manifest.** Tag có thể chỉ trỏ tới image AMD64. Cần inspect manifest và thử pull trên cả hai kiến trúc.

## 11. Checklist trước khi triển khai

- [ ] Xác định ISA của máy nguồn và máy đích (x86_64/amd64, aarch64/arm64).
- [ ] Kiểm tra OS, kernel, ABI, libc và runtime.
- [ ] Lập danh mục binary, package, plugin, driver và dependency bắc cầu.
- [ ] Xác nhận hỗ trợ Arm64 từ nhà cung cấp phần mềm và điều khoản license.
- [ ] Build artifact native cho từng kiến trúc.
- [ ] Tạo và kiểm tra OCI manifest đa kiến trúc nếu dùng container.
- [ ] Kiểm thử trên runner hoặc node native của từng kiến trúc.
- [ ] Xác minh Kubernetes scheduling, node affinity và capacity.
- [ ] Kiểm tra monitoring, logging, backup, security agent và driver.
- [ ] Benchmark latency, throughput, tài nguyên và chi phí theo workload.
- [ ] Triển khai canary, theo dõi ngưỡng và chuẩn bị rollback.
- [ ] Cập nhật IaC, CI/CD, tài liệu vận hành và kế hoạch capacity.

## 12. Ghi nhớ

- **x86-64 và Arm64 là hai ISA khác nhau.** Binary native của kiến trúc này không mặc nhiên chạy trực tiếp trên kiến trúc kia.
- **Tương thích có nhiều lớp:** ISA, ABI, hệ điều hành, runtime, thư viện native, container image và công cụ vận hành đều cần được kiểm tra.
- **Mã nguồn portable không đồng nghĩa artifact portable.** Ứng dụng cần được build và test cho target cụ thể.
- **Container không che giấu ISA của host.** Dùng manifest đa kiến trúc để phân phối đúng image variant cho từng node.
- **Cluster Kubernetes hỗn hợp cần scheduling rõ ràng.** Image, node architecture và affinity phải khớp nhau.
- **Benchmark thực tế quyết định hiệu quả.** So sánh hiệu năng và chi phí trên workload đại diện, có tính đến vận hành và hỗ trợ.
- **Di chuyển theo từng bước.** Kiểm kê, build, test, benchmark, canary và rollback giúp giới hạn rủi ro.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| ISA | Instruction Set Architecture, kiến trúc tập lệnh mà CPU thực thi. |
| x86-64 / AMD64 | Kiến trúc tập lệnh 64-bit thuộc họ x86. |
| Arm64 / AArch64 | Kiến trúc thực thi 64-bit của Arm. |
| Microarchitecture | Cách một CPU cụ thể hiện thực ISA ở cấp phần cứng. |
| ABI | Application Binary Interface, quy ước tương tác giữa các thành phần nhị phân. |
| Binary | Tệp chương trình đã được biên dịch hoặc liên kết để thực thi. |
| Native library | Thư viện chứa mã máy phụ thuộc kiến trúc và nền tảng. |
| Cross-compile | Biên dịch trên một nền tảng để tạo artifact cho nền tảng khác. |
| Runtime | Môi trường thực thi chương trình, ví dụ JVM hoặc .NET runtime. |
| OCI image index | Danh mục trỏ đến các image manifest theo từng platform. |
| Multi-architecture image | Image phát hành nhiều biến thể cho các kiến trúc khác nhau. |
| QEMU | Công cụ giả lập và dịch mã máy, có thể hỗ trợ build/test đa kiến trúc. |
| Canary deployment | Triển khai cho một phần nhỏ traffic trước khi mở rộng. |
| Node affinity | Ràng buộc pod Kubernetes theo label của node. |
| SIMD | Single Instruction, Multiple Data, nhóm lệnh xử lý nhiều phần tử dữ liệu song song. |
