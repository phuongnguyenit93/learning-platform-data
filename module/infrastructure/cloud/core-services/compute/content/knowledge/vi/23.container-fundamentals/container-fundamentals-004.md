# Image đa kiến trúc cho x86 và Arm

Container image thường được build trên máy phát triển hoặc CI rồi chạy trên nhiều loại node trong môi trường cloud. Nếu cụm có cả máy x86-64 và Arm64, image phải chứa đúng binary, thư viện và metadata cho kiến trúc đích. Một binary chỉ dành cho x86-64 có thể build thành công trên máy CI nhưng thất bại khi scheduler đưa container lên node Arm. Image đa kiến trúc giải quyết việc phân phối bằng cách cung cấp các biến thể phù hợp trong cùng một tham chiếu image.

OCI image index, trước đây thường được gọi là Docker manifest list, là cơ chế phổ biến để một tag đại diện cho nhiều image theo hệ điều hành, kiến trúc và đôi khi cả biến thể CPU. Khi client pull image, registry trả về index; container runtime chọn manifest phù hợp với nền tảng của node rồi tải các layer tương ứng.

Bài học này hướng dẫn cách thiết kế, build, kiểm tra và triển khai image đa kiến trúc cho x86 và Arm. Nội dung bao gồm khác biệt binary và thư viện native, cross-compilation, emulation, Docker Buildx, registry, kiểm thử trên phần cứng thật và lập lịch workload trong cụm hỗn hợp. Sau bài học, bạn có thể:

- Giải thích khác biệt giữa image đơn kiến trúc, manifest list và OCI image index.
- Nhận diện nền tảng build và nền tảng chạy bằng OS, architecture và variant.
- Tạo image cho linux/amd64 và linux/arm64 bằng Docker Buildx.
- Viết Dockerfile hỗ trợ build native hoặc cross-compile an toàn.
- Xác minh registry chứa đủ biến thể và runtime chọn đúng image.
- Kiểm thử binary, thư viện native, hiệu năng và hành vi trên cả x86 lẫn Arm.
- Triển khai workload trên cụm compute có nhiều kiến trúc mà không đặt nhầm container lên node.

## 1. Vì sao cần image đa kiến trúc?

Hai máy có thể chạy cùng hệ điều hành Linux và cùng container runtime nhưng sử dụng kiến trúc CPU khác nhau. CPU x86-64 thường được nhận diện là amd64 trong Docker/OCI; Arm 64-bit thường được nhận diện là arm64. Tên kiến trúc trong công cụ container không nhất thiết giống chuỗi mà lệnh hệ điều hành hiển thị.

| Nền tảng | Tên thường gặp trong OCI/Docker | Giá trị uname -m thường thấy |
|---|---|---|
| Linux x86 64-bit | linux/amd64 | x86_64 |
| Linux Arm 64-bit | linux/arm64 | aarch64 |
| Linux Arm 32-bit, variant v7 | linux/arm/v7 | armv7l |

Một binary được biên dịch cho x86-64 không thể mặc nhiên chạy trực tiếp trên CPU Arm64. Tương tự, binary Arm64 không thể chạy trực tiếp trên x86-64 nếu không có lớp mô phỏng hoặc chuyển đổi phù hợp. Việc image có cùng tên tag không làm binary bên trong trở nên tương thích tự động.

### Image đơn kiến trúc

Image đơn kiến trúc chứa một biến thể dành cho một nền tảng cụ thể. Ví dụ, image orders-api:1.4-amd64 chỉ có binary x86-64. Muốn chạy trên Arm, nhóm phải build và phân phối một biến thể riêng như orders-api:1.4-arm64, đồng thời quản lý hai tham chiếu trong hệ thống triển khai.

### Image đa kiến trúc

Image đa kiến trúc cung cấp một tham chiếu chung, chẳng hạn orders-api:1.4, trỏ tới index chứa manifest cho cả linux/amd64 và linux/arm64. Runtime đọc metadata và tự chọn biến thể khớp node.

~~~mermaid
flowchart TD
    T["orders-api:1.4"] --> I["OCI image index"]
    I --> A["Manifest linux/amd64"]
    I --> B["Manifest linux/arm64"]
    A --> AL["Config + layers x86-64"]
    B --> BL["Config + layers Arm64"]
    N1["Node x86-64"] --> T
    N2["Node Arm64"] --> T
    N1 -. "runtime chọn" .-> A
    N2 -. "runtime chọn" .-> B
~~~

Nhờ vậy, manifest index tạo ra một giao diện triển khai thống nhất. Pipeline vẫn phải build và kiểm thử từng biến thể; index chỉ giúp phân phối đúng image cho nền tảng phù hợp.

## 2. OCI image index và manifest hoạt động ra sao?

Một image OCI thường gồm cấu hình image và các layer filesystem. Manifest mô tả config cùng danh sách layer cho một image cụ thể. OCI image index là một cấu trúc cấp cao hơn, chứa nhiều descriptor trỏ tới các manifest khác nhau.

Descriptor trong index có thể mô tả:

- os: hệ điều hành, ví dụ linux.
- architecture: kiến trúc, ví dụ amd64 hoặc arm64.
- variant: biến thể kiến trúc khi cần, ví dụ v7 cho một số nền tảng Arm.
- digest: định danh nội dung của manifest được tham chiếu.
- mediaType và size: loại nội dung cùng kích thước descriptor.

Khi pull một tag đa kiến trúc, runtime lấy index rồi chọn descriptor phù hợp với nền tảng hiện tại. Nó tiếp tục tải manifest và các layer tương ứng. Tag có thể trỏ tới index chung, trong khi digest của từng manifest con khác nhau.

### Tag và digest

Tag như 1.4 hoặc stable là tên dễ đọc nhưng có thể được cập nhật để trỏ sang nội dung khác. Digest như sha256:... nhận diện nội dung bất biến. Trong triển khai production, nên ghi nhận digest đã được kiểm tra để bảo đảm rollout có thể tái lập và rollback chính xác.

Với image đa kiến trúc, cần phân biệt:

- Digest của OCI index: định danh tập manifest cho nhiều nền tảng.
- Digest của manifest con: định danh image cụ thể cho một OS/architecture.
- Digest của từng layer: định danh nội dung layer.

Pin digest của index giúp mọi node dùng cùng một tập biến thể đã phát hành. Runtime vẫn chọn manifest con phù hợp với kiến trúc của nó.

### Runtime không tự chuyển đổi binary

OCI index chỉ chọn image đã được build cho đúng nền tảng. Nó không biên dịch lại binary, không chuyển đổi thư viện native và không đảm bảo ứng dụng tương thích về logic. Nếu index thiếu linux/arm64, một node Arm có thể nhận lỗi không tìm thấy manifest phù hợp khi pull.

## 3. Những thành phần có thể khác nhau giữa x86 và Arm

Khác biệt kiến trúc ảnh hưởng tới nhiều lớp trong image.

### Binary và compiler target

Executable phải được biên dịch cho kiến trúc CPU đích. Ví dụ, Go có thể dùng GOARCH=amd64 hoặc GOARCH=arm64; GCC/Clang dùng target triple và toolchain phù hợp. Một chương trình được build trên x86 không tự trở thành Arm binary khi đóng gói trong image.

### Thư viện native và ABI

Ứng dụng có thể phụ thuộc vào OpenSSL, libstdc++, database driver native, codec, thư viện xử lý ảnh hoặc extension C/C++. Mỗi thư viện phải có bản build phù hợp với kiến trúc và ABI của runtime.

Không nên sao chép thư viện .so từ stage x86 sang image Arm. Cần cài package đúng kiến trúc hoặc build từ source bằng toolchain đích.

### Runtime và package có native extension

Một số package Python, Node.js, Ruby, Java JNI hoặc .NET native dependency có thành phần biên dịch theo kiến trúc. Package manager có thể chọn wheel hoặc binary package khác nhau theo platform. Nếu không có artifact tương thích, build có thể thất bại hoặc rơi về build-from-source.

### Base image

Nhiều base image chính thức có hỗ trợ nhiều kiến trúc, nhưng không phải mọi tag hoặc biến thể đều hỗ trợ giống nhau. Base image nội bộ, image vendor và image chứa agent độc quyền cần được kiểm tra manifest trước khi dùng.

### Tập lệnh CPU và tối ưu hóa

Binary có thể được build với các tập lệnh CPU cụ thể. Một binary x86-64 được tối ưu cho AVX-512 có thể không chạy trên instance x86 không hỗ trợ tập lệnh đó. Arm cũng có các đặc tính như NEON hoặc SVE tùy CPU. Nên chọn baseline instruction set tương thích với toàn bộ nhóm instance mục tiêu hoặc phát hành biến thể tối ưu có điều kiện rõ ràng.

### Hành vi và hiệu năng

Ngay cả khi binary chạy đúng trên cả hai kiến trúc, hiệu năng có thể khác do số core, cache, memory bandwidth, NUMA, compiler, runtime và loại instance. Không suy ra rằng cùng số vCPU đồng nghĩa cùng throughput. Benchmark workload đại diện trên từng loại máy trước khi quyết định tỷ lệ phân bổ.

## 4. Kiểm tra kiến trúc của máy build và máy chạy

Trên Linux:

~~~bash
uname -s
uname -m
getconf LONG_BIT
~~~

Trong Docker:

~~~bash
docker version --format '{{.Server.Os}}/{{.Server.Arch}}'
docker info --format '{{.OSType}}/{{.Architecture}}'
~~~

Trên Dockerfile, BuildKit cung cấp các build argument tự động:

- BUILDPLATFORM: nền tảng của builder.
- BUILDOS, BUILDARCH, BUILDVARIANT: hệ điều hành, kiến trúc và variant của builder.
- TARGETPLATFORM: nền tảng image đích.
- TARGETOS, TARGETARCH, TARGETVARIANT: hệ điều hành, kiến trúc và variant đích.

Ví dụ, CI chạy trên linux/amd64 nhưng cần tạo image linux/arm64. Khi đó BUILDARCH=amd64 và TARGETARCH=arm64. Việc phân biệt hai nhóm biến này rất quan trọng khi cross-compile.

## 5. Build image đa kiến trúc bằng Docker Buildx

Docker Buildx là giao diện build dựa trên BuildKit, hỗ trợ build cho nhiều nền tảng và xuất kết quả thành image manifest/index. Một builder có thể dùng native node cho nhiều kiến trúc hoặc dùng emulation để chạy lệnh build của kiến trúc đích.

### Kiểm tra Buildx

~~~bash
docker buildx version
docker buildx ls
~~~

Tạo builder dùng driver docker-container nếu môi trường chưa có builder phù hợp:

~~~bash
docker buildx create --name multiarch-builder --driver docker-container --use
docker buildx inspect --bootstrap
~~~

Lệnh inspect --bootstrap khởi tạo builder và hiển thị các platform được hỗ trợ. Danh sách có thể phụ thuộc vào QEMU/binfmt hoặc các node builder đã đăng ký.

### Build và push hai kiến trúc

Giả sử Dockerfile hỗ trợ đa kiến trúc và registry đã đăng nhập:

~~~bash
docker login registry.example.com

docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/team/orders-api:1.4.0 \
  --push \
  .
~~~

Buildx build biến thể cho từng platform rồi push manifest/index lên registry. Khi dùng multi-platform, --push là cách phổ biến để công bố kết quả. --load trong Docker image store cổ điển thường chỉ nạp một platform; khả năng lưu multi-platform local phụ thuộc image store và phiên bản Docker. Không giả định --load luôn tạo một index đa kiến trúc.

Kiểm tra kết quả:

~~~bash
docker buildx imagetools inspect registry.example.com/team/orders-api:1.4.0
~~~

Kết quả cần có descriptor cho các platform dự kiến, ví dụ linux/amd64 và linux/arm64. Nếu chỉ thấy một platform, không triển khai tag đó lên cụm hỗn hợp trước khi sửa pipeline.

## 6. Viết Dockerfile hỗ trợ cross-compilation

Với ứng dụng thuần Go không cần CGO, có thể biên dịch binary cho target architecture trên builder host khác kiến trúc. Cách này giảm phụ thuộc vào emulation trong giai đoạn compile.

~~~dockerfile
# syntax=docker/dockerfile:1

FROM --platform=$BUILDPLATFORM golang:1.23 AS build
WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download
COPY . .

ARG TARGETOS
ARG TARGETARCH
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags="-s -w" -o /out/orders-api ./cmd/orders-api

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/orders-api /orders-api
USER nonroot:nonroot
ENTRYPOINT ["/orders-api"]
~~~

Ở stage build, BUILDPLATFORM giữ compiler chạy trên kiến trúc của builder. TARGETOS và TARGETARCH chỉ định binary đầu ra. Stage runtime không ép platform về builder, nên BuildKit chọn base image runtime tương ứng với target platform. Base image distroless trong ví dụ cần được kiểm tra hỗ trợ đầy đủ các kiến trúc mục tiêu trước khi dùng.

Đây là ví dụ cho binary Go thuần không dùng CGO. Nếu ứng dụng phụ thuộc C library, cần toolchain cross-compile, sysroot và thư viện đúng target; chỉ đặt GOARCH là chưa đủ.

### Build native theo từng platform

Với ứng dụng C/C++, Java có JNI hoặc package native phức tạp, build trên runner native cho từng kiến trúc thường đơn giản và đáng tin cậy hơn:

1. Runner x86 build image linux/amd64.
2. Runner Arm build image linux/arm64.
3. Mỗi runner chạy test và tạo artifact riêng.
4. Pipeline ghép các manifest thành index chung.

Ưu điểm là compiler, package manager và test chạy trực tiếp trên kiến trúc đích. Đổi lại, CI cần runner cho cả hai loại CPU và quản lý artifact giữa các job.

## 7. Emulation và QEMU

Nếu chỉ có builder x86 nhưng cần build image Arm, QEMU user-mode kết hợp binfmt_misc có thể cho phép thực thi binary Arm trong môi trường build x86. Buildx thường phát hiện các platform được hỗ trợ bởi builder.

Trên Linux, một số môi trường thiết lập handler QEMU thông qua image tonistiigi/binfmt:

~~~bash
docker run --privileged --rm tonistiigi/binfmt --install arm64,amd64
docker buildx inspect --bootstrap
~~~

Lệnh cài binfmt cần quyền privileged và chỉ nên chạy trong môi trường build được kiểm soát. CI managed hoặc Docker Desktop có thể đã cấu hình emulation; không nên cài lại một cách máy móc.

### Khi nào dùng emulation?

- Build hoặc test smoke nhẹ cho kiến trúc chưa có runner native.
- Tạo image có package manager hoặc script cần thực thi binary target trong build.
- Kiểm tra nhanh rằng entrypoint và một số lệnh khởi động hoạt động.

### Giới hạn của emulation

- Build có thể chậm đáng kể so với native.
- Một số thao tác kernel, syscall hoặc thiết bị không được mô phỏng đầy đủ.
- Kết quả hiệu năng không đại diện cho CPU thật.
- Một số ứng dụng có JIT, SIMD hoặc native extension có thể gặp khác biệt.
- Build nặng có thể hết thời gian CI hoặc tạo tải lớn cho builder.

Emulation hữu ích để mở rộng khả năng build nhưng không thay thế kiểm thử trên máy Arm thật trước khi phát hành workload quan trọng.

## 8. Xử lý dependency native và package đa kiến trúc

Đây là một trong các nguồn lỗi phổ biến nhất. Image có manifest arm64 nhưng bên trong vẫn có thư viện x86 sẽ không chạy đúng.

### Package hệ điều hành

Khi cài package trong stage target, package manager cần chạy cho đúng kiến trúc. Nếu stage đó đang chạy dưới emulation, package manager thường chọn package theo target root filesystem. Nếu cross-compile thủ công, cần xác định rõ package sysroot và thư viện đích.

Không sao chép thư mục /usr/lib hoặc binary từ host build sang image target nếu chưa xác minh kiến trúc và ABI của mọi file.

### Python wheels

Python package có extension native thường phát hành wheel theo ABI, kiến trúc và libc. Một wheel manylinux x86-64 không dùng được trên Arm64. Nếu không có wheel phù hợp, pip có thể build từ source và cần compiler, header cùng thư viện hệ thống.

Hãy xác minh:

- Wheel tương thích Python version và ABI.
- Platform tag phù hợp x86_64 hoặc aarch64.
- libc là glibc hay musl và package hỗ trợ loại nào.
- Build-from-source có toolchain và dependency đích.

### Node.js và native addon

Một số npm package tải binary prebuilt theo platform hoặc build addon bằng node-gyp. CI phải bảo đảm addon được build cho target architecture và phiên bản Node ABI đúng. Không copy node_modules từ một host x86 sang image Arm nếu trong đó có native addon.

### Java và JNI

Bytecode Java thuần thường độc lập kiến trúc, nhưng JNI library, native compression, cryptography provider hoặc agent có binary native vẫn phụ thuộc CPU và libc. Cần kiểm tra toàn bộ thư viện được nạp khi ứng dụng chạy.

### libc và base image

Alpine thường dùng musl; nhiều image Debian/Ubuntu dùng glibc. Một binary build cho glibc không nhất thiết chạy trên musl. Kiến trúc CPU đúng nhưng libc hoặc ABI không tương thích vẫn gây lỗi kiểu not found, exec format error hoặc thiếu symbol khi khởi chạy.

## 9. Kiểm tra image và binary trước khi phát hành

### Kiểm tra index

~~~bash
docker buildx imagetools inspect registry.example.com/team/orders-api:1.4.0
~~~

Xác nhận index chứa đúng OS, architecture và variant cần hỗ trợ. Kiểm tra cả base image và image phụ thuộc nếu pipeline có nhiều stage hoặc tải binary ngoài.

### Kiểm tra image đang chạy

Trong container:

~~~bash
uname -m
cat /etc/os-release
~~~

Trên máy Docker:

~~~bash
docker image inspect registry.example.com/team/orders-api:1.4.0 \
  --format '{{.Os}}/{{.Architecture}}'
~~~

Lưu ý docker image inspect trên một máy local cho biết biến thể đã được pull hoặc nạp vào image store tại máy đó, không thay thế việc kiểm tra index trong registry.

### Kiểm tra executable

Trên Linux có thể dùng:

~~~bash
file /orders-api
readelf -h /orders-api
ldd /orders-api
~~~

file và readelf giúp nhận diện định dạng và machine architecture. ldd cho biết dynamic library được phân giải trên hệ thống hiện tại; không nên chạy ldd với binary không tin cậy. Với binary static, ldd có thể không liệt kê dependency động.

### Kiểm tra lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| exec format error | Binary sai kiến trúc hoặc file không phải executable hợp lệ | file, readelf, target platform và Dockerfile |
| no matching manifest for linux/arm64 | Index không có descriptor Arm64 | imagetools inspect, pipeline publish |
| not found dù file tồn tại | Thiếu dynamic loader hoặc libc không tương thích | readelf -l, ldd, base image |
| undefined symbol | Native library/ABI không tương thích | Phiên bản thư viện, build toolchain và runtime |
| Chạy được nhưng chậm | Khác biệt CPU, SIMD, memory hoặc dependency | Benchmark native trên instance đích |
| Một số node pull được, node khác không | Tag bị thay đổi, cache, registry mirror hoặc architecture khác | Pin digest, kiểm tra index và runtime logs |

## 10. Kiểm thử trên cả x86 và Arm

Một pipeline đa kiến trúc cần kiểm tra từng biến thể. Tối thiểu nên có:

1. Build thành công cho từng target.
2. Pull image trên runner hoặc node có kiến trúc tương ứng.
3. Kiểm tra entrypoint và health check.
4. Chạy unit/integration test phù hợp.
5. Kiểm tra kết nối tới database, storage, queue và dịch vụ ngoài.
6. Kiểm tra native library, TLS, compression và codec nếu ứng dụng dùng.
7. Đo startup time, memory và CPU trên phần cứng thật.
8. Kiểm tra graceful shutdown và xử lý tín hiệu.

### Kiểm thử chéo và kiểm thử native

Có thể dùng docker run --platform linux/arm64 trên host x86 nếu emulation được cấu hình. Điều này hữu ích cho smoke test nhưng không chứng minh hiệu năng, tính ổn định của driver hoặc hành vi trên CPU Arm thật.

Với workload quan trọng, hãy chạy ít nhất một canary native trên mỗi kiến trúc. Kiểm tra các trường hợp có thể phụ thuộc CPU feature, atomic operation, concurrency, memory ordering, codec hoặc thư viện native.

### Benchmark và lựa chọn instance

Không nên giả định một instance Arm có cùng số vCPU sẽ có hiệu năng giống instance x86. Hãy đo:

- Throughput và p95/p99 latency.
- CPU utilization, throttling và memory bandwidth.
- RSS, heap, garbage collection và page fault.
- I/O và network throughput.
- Startup time và thời gian warm-up.
- Chi phí trên một request hoặc job thành công.

Một workload có thể chạy tốt hơn trên Arm do hiệu năng trên mỗi watt hoặc giá/hiệu năng, nhưng điều đó phụ thuộc loại CPU, runtime và ứng dụng. Quyết định nên dựa trên benchmark đại diện.

## 11. Triển khai trên cụm compute hỗn hợp

Khi cụm có node x86 và Arm, scheduler cần biết workload tương thích với kiến trúc nào. Image đa kiến trúc cho phép dùng cùng tag, nhưng không tự bảo đảm node có đủ tài nguyên hoặc workload đã được kiểm thử.

### Kubernetes

Kubernetes gắn label chuẩn cho node:

- kubernetes.io/arch=amd64
- kubernetes.io/arch=arm64

Nếu image hỗ trợ cả hai kiến trúc, pod có thể chạy trên cả hai loại node. Nếu ứng dụng chỉ hỗ trợ một kiến trúc, dùng node selector hoặc node affinity để giới hạn placement.

Ví dụ chỉ cho workload chạy trên Arm64:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: image-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: image-worker
  template:
    metadata:
      labels:
        app: image-worker
    spec:
      nodeSelector:
        kubernetes.io/arch: arm64
      containers:
        - name: worker
          image: registry.example.com/team/image-worker:2.1.0
          resources:
            requests:
              cpu: "1"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
~~~

Với image đa kiến trúc, có thể bỏ nodeSelector nếu workload đã được kiểm thử trên cả hai loại node và scheduler có thể đặt pod theo tài nguyên sẵn có. Nếu cần ưu tiên một kiến trúc hoặc tránh node có accelerator/driver không tương thích, dùng node affinity và taint/toleration theo thiết kế cụm.

### Các thành phần cần kiểm tra trong cluster

- Node pool có label kiến trúc chính xác.
- DaemonSet, CNI, CSI, monitoring agent và security agent hỗ trợ kiến trúc của node.
- Sidecar và init container cũng phải có image tương thích.
- Admission policy hoặc policy triển khai không ghim nhầm image đơn kiến trúc.
- Autoscaler có thể tạo node pool đúng kiến trúc và đủ quota.
- Pod disruption và rollout không dồn toàn bộ replica vào một kiến trúc.

Một ứng dụng chính có image đa kiến trúc nhưng sidecar chỉ có amd64 vẫn sẽ thất bại trên Arm. Cần kiểm tra toàn bộ container trong pod.

### VM và container service managed

Với VM group hoặc managed container service, xác minh instance family hỗ trợ kiến trúc mong muốn và nền tảng có cung cấp node pool tương ứng. Một số dịch vụ có thể hỗ trợ Arm cho một số region hoặc loại instance nhưng không phải mọi tính năng. Cần kiểm tra compatibility của agent, extension, monitoring và runtime do nền tảng quản lý.

## 12. Thiết kế pipeline CI/CD cho image đa kiến trúc

~~~mermaid
flowchart TD
    S["Source + Dockerfile"] --> B["Build cho amd64 và arm64"]
    B --> T["Test từng biến thể"]
    T --> Q["Quét lỗ hổng và tạo SBOM"]
    Q --> P["Push manifest/layers"]
    P --> I["Tạo hoặc xác minh OCI index"]
    I --> V["Ký và phát hành digest"]
    V --> C["Canary trên node x86 và Arm"]
    C --> R["Rollout có kiểm soát"]
~~~

### Các bước quan trọng

1. **Source pinning:** khóa version dependency và base image bằng digest khi cần.
2. **Build matrix:** build target linux/amd64 và linux/arm64.
3. **Test theo platform:** chạy test trên runner native hoặc môi trường emulation có kiểm soát.
4. **Security scan:** quét từng biến thể và các layer; lưu kết quả theo digest.
5. **SBOM và provenance:** tạo Software Bill of Materials và thông tin nguồn gốc build cho từng artifact hoặc index theo công cụ.
6. **Publish:** push các manifest và index vào registry.
7. **Verify:** kiểm tra index có đủ descriptor và digest mong đợi.
8. **Sign:** ký digest đã phát hành và xác minh chữ ký trước deploy.
9. **Canary:** triển khai một phần replica trên mỗi kiến trúc.
10. **Rollout:** mở rộng dần sau khi health check và metrics đạt.

### Quản lý cache build

BuildKit cache giúp giảm thời gian build, nhưng cache phải được dùng đúng theo target architecture và toolchain. Tránh tái sử dụng artifact native của amd64 cho arm64 chỉ vì cache key không phân biệt target. Đưa TARGETPLATFORM, version compiler và dependency vào cache key khi cần.

Không để cache build chứa credential hoặc dữ liệu nhạy cảm. Build secret nên được truyền bằng cơ chế secret mount của BuildKit, không ghi vào layer hoặc build argument công khai.

## 13. Bảo mật và chuỗi cung ứng phần mềm

Image đa kiến trúc có nhiều manifest và layer, vì vậy việc kiểm soát nguồn gốc cần áp dụng cho toàn bộ tập artifact:

- Dùng base image chính thức hoặc đã được tổ chức phê duyệt.
- Pin digest để build tái lập.
- Quét lỗ hổng cho từng biến thể, vì package set có thể khác nhau.
- Tạo SBOM phản ánh đúng binary và package trong từng image.
- Lưu provenance gồm source commit, builder, toolchain và target platform.
- Ký digest index hoặc artifact theo quy trình ký của tổ chức.
- Chỉ cho phép registry và workload identity được phê duyệt.
- Xác minh chữ ký và policy trước khi triển khai.

Một image amd64 đã quét không chứng minh image arm64 an toàn. Hai biến thể có thể chứa package hoặc dependency khác nhau do package manager chọn artifact khác theo kiến trúc.

## 14. Ví dụ: build một image Go đa kiến trúc

Giả sử API viết bằng Go, không dùng CGO và cần chạy trên VM x86-64 lẫn Arm64. Dockerfile ở phần 6 đã dùng BUILDPLATFORM để giữ compiler native trên builder và TARGETOS/TARGETARCH để tạo binary đích.

Quy trình thực hiện:

~~~bash
# Xem builder và platform hỗ trợ
docker buildx inspect --bootstrap

# Build và publish cả hai kiến trúc
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t registry.example.com/team/orders-api:1.4.0 \
  --push .

# Kiểm tra OCI index
docker buildx imagetools inspect \
  registry.example.com/team/orders-api:1.4.0
~~~

Sau khi publish:

1. Pull tag trên runner x86 và kiểm tra image architecture.
2. Pull cùng tag trên runner Arm và kiểm tra image architecture.
3. Chạy health check và integration test trên cả hai.
4. Chạy benchmark trên instance native.
5. Ghi nhận index digest và ký artifact.
6. Triển khai canary lên từng node pool rồi mới mở rộng.

Nếu ứng dụng cần CGO, nhóm phải bổ sung cross toolchain hoặc build native trên từng kiến trúc. Không được giữ CGO_ENABLED=0 nếu ứng dụng thực sự cần native library.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách khắc phục |
|---|---|---|
| exec format error trên Arm | Binary x86 được đóng vào image Arm hoặc ngược lại | Kiểm tra file, readelf, TARGETARCH và build stage |
| Registry báo không có manifest phù hợp | Index thiếu platform cần chạy | Build/push platform còn thiếu và xác minh lại index |
| Runtime thiếu .so | Copy native library sai kiến trúc hoặc sai ABI | Cài/build dependency trong target stage |
| Python package không cài trên Arm | Không có wheel phù hợp hoặc thiếu toolchain | Kiểm tra wheel tag, build dependency từ source hoặc chọn version hỗ trợ |
| Node addon lỗi khi khởi chạy | node_modules chứa binary của kiến trúc khác | Cài dependency trong target build stage |
| Image chạy được nhưng chậm trên một kiến trúc | Compiler flag, CPU feature hoặc dependency khác | Benchmark native và profile theo platform |
| Pod pending hoặc không schedule | Node selector/affinity không khớp label hoặc thiếu node capacity | Kiểm tra node labels, taint, affinity và autoscaler |
| Sidecar không chạy trên Arm | Image phụ trợ chỉ có amd64 | Thay image hỗ trợ Arm hoặc giới hạn pod vào node tương thích |
| CI tái sử dụng artifact sai | Cache key không phân biệt target architecture | Tách cache theo target và toolchain |

## 16. Checklist trước khi phát hành image đa kiến trúc

- [ ] Đã xác định rõ các platform mục tiêu như linux/amd64 và linux/arm64.
- [ ] Base image hỗ trợ tất cả platform mục tiêu.
- [ ] Mọi executable và native library được build đúng kiến trúc.
- [ ] Dependency Python/Node/Java/JNI hoặc package native đã được kiểm tra.
- [ ] Compiler flags không yêu cầu CPU feature ngoài baseline của node pool.
- [ ] Buildx builder hỗ trợ platform cần thiết.
- [ ] Registry có OCI index với đủ descriptor và digest.
- [ ] Đã kiểm tra index bằng docker buildx imagetools inspect.
- [ ] Đã chạy smoke/integration test trên từng kiến trúc.
- [ ] Đã benchmark trên phần cứng native với workload đại diện.
- [ ] Sidecar, init container, DaemonSet và agent đều tương thích.
- [ ] Kubernetes node selector/affinity phù hợp với khả năng image.
- [ ] SBOM, scan, provenance và chữ ký áp dụng cho từng biến thể.
- [ ] Digest phát hành được ghi nhận để rollback và tái lập.
- [ ] Canary trên x86 và Arm đạt health check trước rollout rộng.

## 17. Bài tập vận dụng

Một nhóm triển khai dịch vụ xử lý ảnh trên cụm Kubernetes gồm 70% node x86-64 và 30% node Arm64. Image hiện tại được build trên runner x86, chạy tốt trên node x86 nhưng pod thất bại trên Arm với lỗi exec format error. Dockerfile dùng base image chính thức, sau đó copy thư mục build từ máy CI vào image. Ứng dụng có một thư viện native để giải mã ảnh.

1. Vì sao base image hỗ trợ Arm nhưng container vẫn lỗi trên node Arm?
2. Cần kiểm tra những metadata nào trong OCI index và executable?
3. Hãy đề xuất hai phương án build image cho cả hai kiến trúc: cross-compile và native build matrix.
4. Thư viện native cần được xử lý thế nào để bảo đảm đúng kiến trúc và ABI?
5. Cần kiểm thử những thành phần nào ngoài container chính trước khi mở rộng rollout?
6. Nếu hiệu năng xử lý ảnh trên Arm khác x86, nhóm nên so sánh những chỉ số nào?

Gợi ý: thư mục build có thể chứa binary x86 được copy nguyên vào image Arm. Cần kiểm tra file, readelf, target platform và index; build lại executable cùng thư viện native cho từng target. Có thể cross-compile nếu toolchain và sysroot hỗ trợ, hoặc chạy build native trên hai loại runner rồi ghép manifest index. Kiểm tra sidecar, init container, agent, health check, startup và benchmark throughput/latency/CPU/memory trên phần cứng thật.

## Kết luận

Image đa kiến trúc dùng OCI image index để một tham chiếu chung trỏ tới các manifest phù hợp với từng OS và kiến trúc CPU. Cơ chế này đơn giản hóa triển khai trên cụm x86 và Arm, nhưng không tự chuyển đổi binary hoặc dependency. Muốn phát hành an toàn, pipeline phải build đúng target, xử lý thư viện native và ABI, xác minh index, kiểm thử từng biến thể trên phần cứng phù hợp, đồng thời kiểm tra toàn bộ sidecar và thành phần nền tảng. Kết hợp digest bất biến, SBOM, provenance, chữ ký và canary theo từng kiến trúc giúp image có thể tái lập, kiểm toán và triển khai ổn định.
