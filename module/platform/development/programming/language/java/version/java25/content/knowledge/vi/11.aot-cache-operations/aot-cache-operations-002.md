# Tạo cache trong pipeline xây dựng và gắn cache với đúng phiên bản ứng dụng

> **Chương:** Vận hành AOT  
> **Phiên bản:** JDK 25 / HotSpot.  
> **Mục tiêu:** Tạo Ahead-of-Time (AOT) cache từ workload đại diện, đóng gói cache cùng đúng build ứng dụng, sử dụng cache khi production khởi động và tái tạo khi môi trường tương thích thay đổi.

## 1. Bài toán: cache tốt nhưng gắn nhầm ứng dụng

Một dịch vụ Java chạy trong container có thời gian khởi động dài do phải nạp nhiều lớp, phân tích cấu trúc lớp và liên kết các thành phần trước khi xử lý request. Nhóm vận hành muốn tận dụng AOT cache để giảm startup và warm-up.

Nếu pipeline tạo cache từ một build nhưng production triển khai build khác, JVM có thể không dùng được cache. Tình huống tương tự xảy ra khi:

- Cache được tạo bằng một bản JDK khác với bản chạy production.
- Cache được tạo trên Linux x86-64 nhưng triển khai lên Linux ARM64.
- JAR hoặc classpath/module-path thay đổi sau khi training.
- Runtime bổ sung tùy chọn hoặc công cụ instrumentation không tương thích.
- Workload training không đại diện cho đường chạy thật của ứng dụng.

AOT cache là **tối ưu hóa gắn với một ứng dụng và môi trường cụ thể**. Nó không phải file cache chung cho mọi ứng dụng Java, không thay thế JAR, và không làm cho bytecode chạy mà không cần JVM.

Sau bài học, bạn có thể:

1. Phân biệt training, assembly và production.
2. Tạo cache bằng luồng ngắn với `-XX:AOTCacheOutput`.
3. Tạo riêng `.aotconfig` và `.aot` trong pipeline nhiều bước.
4. Chạy workload training có tính đại diện.
5. Gắn cache với đúng artifact, JDK release, OS và CPU architecture.
6. Chọn `AOTMode=auto` trong production để có đường chạy dự phòng.
7. Dùng `-Xlog:aot` để xác minh cache được nạp hay bị bỏ qua.
8. Đo hiệu quả trước/sau bằng cùng môi trường và workload.

## 2. AOT cache là gì và giúp gì?

AOT cache là một container chứa các hiện vật tối ưu hóa được chuẩn bị trước khi ứng dụng chạy. Trong JDK 25, tài liệu launcher mô tả cache hiện chứa **Java classes và heap objects**. Cache giúp JVM giảm một phần công việc ở startup và warm-up; nó không biến ứng dụng thành native executable.

AOT cache được giới thiệu từ JDK 24 qua JEP 483 (Ahead-of-Time Class Loading and Linking). Java 25 bổ sung JEP 514 (Ahead-of-Time Command-Line Ergonomics), giúp đơn giản hóa các lệnh tạo và sử dụng cache cho các trường hợp phổ biến.

~~~mermaid
flowchart LR
    A["Application artifact\nJAR / classpath / module path"] --> B["Training\nchạy workload đại diện"]
    B --> C["AOT configuration\n.aotconfig"]
    C --> D["Assembly\nJVM tạo cache"]
    D --> E["AOT cache\n.aot"]
    E --> F["Production JVM\nnạp cache tương thích"]
    A --> F
~~~

Lợi ích kỳ vọng:

- Giảm thời gian nạp và liên kết lớp trong một số ứng dụng.
- Giảm công việc lặp lại ở giai đoạn startup.
- Cải thiện warm-up bằng việc tái sử dụng các tối ưu hóa được chuẩn bị trước.
- Có thể giảm độ trễ khởi động trong môi trường scale-out, nơi nhiều instance cùng được tạo.

AOT cache **không bảo đảm** mọi ứng dụng sẽ nhanh hơn ở mọi môi trường. Hiệu quả phụ thuộc cấu trúc ứng dụng, lượng class được sử dụng, workload training, JVM options, phần cứng và cách đo.

### Không nhầm với các khái niệm khác

| Khái niệm | Vai trò |
|---|---|
| AOT cache của HotSpot | Cache các hiện vật tối ưu hóa như class và heap objects để JVM sử dụng khi chạy ứng dụng |
| CDS (Class Data Sharing) | Cơ chế chia sẻ dữ liệu lớp; AOT cache mở rộng hướng tối ưu hóa này |
| JIT compilation | Biên dịch động trong lúc ứng dụng chạy, dựa trên hành vi runtime |
| GraalVM Native Image | Tạo executable native bằng quy trình build riêng; không phải file `.aot` của HotSpot |
| JEP 515 — AOT Method Profiling | Cải thiện startup bằng cách làm cho method-execution profiles từ lần chạy trước sẵn có khi JVM khởi động; đây là cải tiến liên quan đến AOT nhưng không nên đồng nhất nó với quy trình đóng gói `.aot` ở bài này |

## 3. Ba giai đoạn trong vòng đời cache

| Giai đoạn | JVM làm gì? | Đầu vào | Đầu ra |
|---|---|---|---|
| **Training / Record** | Chạy ứng dụng và thu thập thông tin tối ưu hóa từ workload | JAR/module/classpath và workload đại diện | `.aotconfig` hoặc dữ liệu ghi cache |
| **Assembly / Create** | Đọc thông tin training và tạo AOT cache | `.aotconfig`, cùng ứng dụng tương ứng | `.aot` |
| **Production** | Chạy ứng dụng và nạp cache tương thích | JAR và `.aot` phù hợp | Ứng dụng chạy với AOT optimizations |

~~~mermaid
flowchart TD
    A["Build ứng dụng"] --> B["Training trên đúng artifact"]
    B --> C{"Đã có dữ liệu training?"}
    C -->|Chưa| B
    C -->|Có| D["Assembly tạo .aot"]
    D --> E{"Cache tương thích production?"}
    E -->|Có| F["Nạp cache và chạy"]
    E -->|Không, auto| G["Bỏ cache, chạy bình thường"]
    E -->|Không, on| H["Fail fast để điều tra"]
~~~

**Training không phải benchmark ngẫu nhiên.** JVM cần nhìn thấy những đường chạy thực tế mà ứng dụng thường thực hiện: khởi tạo framework, đăng ký component, tải cấu hình, kết nối các adapter cần thiết và xử lý một số request đại diện. Nếu chỉ chạy ứng dụng rồi thoát ngay, cache có thể không phản ánh các class/đường đi quan trọng.

Training không nên tạo dữ liệu production thật hoặc gửi thông điệp ra hệ thống bên ngoài. Dùng môi trường test/staging và dữ liệu giả lập, sandbox hoặc bản sao đã làm sạch.

## 4. Điều kiện tương thích: cache thuộc về đúng tổ hợp nào?

Theo tài liệu `java` của JDK 25, AOT cache gắn với tổ hợp:

1. **Ứng dụng:** được xác định qua cách khởi chạy như `-classpath`, `-jar` hoặc `--module-path`.
2. **JDK release:** cache phải phù hợp với bản JDK đã tạo nó.
3. **OS và CPU architecture:** ví dụ Linux x86-64, Linux AArch64, Windows x64.

Nếu một trong các yếu tố này thay đổi, phải tạo lại cache. Ngoài ra, một số JVM options có thể khiến cache không tương thích; tài liệu JEP 483 nêu các trường hợp liên quan tới thay đổi class loading và instrumentation.

### Quy tắc gắn cache với build

Không nên đặt tên cache chung chung như:

~~~text
app.aot
~~~

Trong pipeline nhiều nhánh hoặc nhiều kiến trúc, hãy lưu cache theo fingerprint của build và môi trường, ví dụ:

~~~text
artifacts/
└── aot/
    └── order-service/
        └── 2.7.4/
            └── jdk-25.0.x-linux-x86_64/
                ├── app.aotconfig
                └── app.aot
~~~

Tên trên là quy ước tổ chức do nhóm tự chọn, không phải định dạng bắt buộc của JVM. Có thể bổ sung hash JAR, commit SHA, dependency lock hoặc build ID để tránh nhầm cache giữa hai artifact cùng version.

**Không tái sử dụng cache** chỉ vì tên JAR hoặc version hiển thị giống nhau. Nếu bytes của JAR, classpath/module-path, JDK release, OS hoặc architecture thay đổi, cần đánh giá lại và thường phải training/assembly lại.

## 5. Cách đơn giản: tạo cache bằng AOTCacheOutput

Với JDK 25, cách ngắn nhất là chạy ứng dụng cùng `-XX:AOTCacheOutput`:

~~~bash
java -XX:AOTCacheOutput=build/aot/app.aot -jar build/libs/order-service.jar
~~~

Khi không chỉ định `AOTMode`, JVM dùng chế độ `auto`. Nếu có `AOTCacheOutput`, chế độ này tự chuyển sang `record` để training. Khi quá trình training kết thúc, JVM khởi chạy một JVM thứ hai để thực hiện assembly và ghi cache vào file đã chỉ định.

Đường đi đơn giản:

1. Xây dựng đúng JAR sẽ đưa lên production.
2. Chạy lệnh trên trong môi trường training.
3. Gửi workload đại diện đến ứng dụng.
4. Kết thúc tiến trình training theo cách phù hợp; với một service dài hạn, có thể chủ động kết thúc ghi bằng `jcmd` như mục 7.
5. Xác nhận file `.aot` được tạo.
6. Đóng gói `.aot` cùng đúng JAR và runtime target.

Nếu tiến trình training kết thúc tự nhiên, JVM có thể tự hoàn tất việc ghi và assembly. Với một service chạy liên tục, đừng đợi nó tự thoát; hãy dùng cách record có kiểm soát.

### Tạo cache từ workload có thời hạn

Ví dụ cho một ứng dụng ngắn hạn hoặc một kịch bản training tự kết thúc:

~~~bash
mkdir -p build/aot

java -XX:AOTCacheOutput=build/aot/order-service.aot \
     -jar build/libs/order-service.jar \
     --spring.profiles.active=aot-training
~~~

`aot-training` chỉ là tên profile ví dụ của ứng dụng Spring Boot. Profile này cần được nhóm xây dựng để gọi các luồng nghiệp vụ đại diện, sử dụng dependency sandbox và không gửi tác dụng phụ đến production.

Nếu ứng dụng là HTTP server, cần có một cơ chế điều khiển workload và kết thúc training rõ ràng. Phần sau trình bày cách tách riêng `.aotconfig` và `.aot` để pipeline dễ kiểm soát hơn.

## 6. Pipeline nhiều bước: record, create, production

Cách tách ba giai đoạn phù hợp khi CI/CD cần lưu riêng dữ liệu training và cache, kiểm tra từng bước, hoặc chạy training trên service tồn tại lâu.

Giả sử artifact đã build là:

~~~text
build/libs/order-service.jar
~~~

Tạo thư mục output:

~~~bash
mkdir -p build/aot
~~~

### 6.1. Training: tạo AOT configuration

Khởi chạy JVM ở chế độ `record`:

~~~bash
java \
  -XX:AOTMode=record \
  -XX:AOTConfiguration=build/aot/order-service.aotconfig \
  -jar build/libs/order-service.jar \
  --spring.profiles.active=aot-training
~~~

Ở chế độ này, JVM thu thập thông tin training và ghi vào `.aotconfig`. Ứng dụng thực sự chạy, vì vậy hãy gửi workload đại diện trong lúc tiến trình còn hoạt động.

Đối với service chạy lâu dài, lấy PID bằng `jcmd -l`, sau đó kết thúc recording:

~~~bash
jcmd -l
jcmd <PID> AOT.end_recording
~~~

Thay `<PID>` bằng process ID thực tế. Lệnh `AOT.end_recording` kết thúc việc ghi AOT đang chạy và ghi kết quả ra file được chỉ định bởi `AOTConfiguration` và/hoặc `AOTCacheOutput`. Nếu không dùng `jcmd`, kết thúc training process theo quy trình shutdown đã kiểm soát; JVM cũng ghi dữ liệu khi tiến trình thoát.

### 6.2. Assembly: tạo file .aot

Dùng chính artifact ứng dụng và configuration đã thu thập:

~~~bash
java \
  -XX:AOTMode=create \
  -XX:AOTConfiguration=build/aot/order-service.aotconfig \
  -XX:AOTCache=build/aot/order-service.aot \
  -jar build/libs/order-service.jar
~~~

Ở `create`, JVM đọc dữ liệu training và tạo cache. **Ứng dụng không được chạy trong giai đoạn assembly**; lệnh vẫn cần thông tin ứng dụng để xác định cache gắn với app nào.

Trong JDK 25, `-XX:AOTCache` được dùng làm đường dẫn output ở chế độ `create`; khi production, cùng option này là đường dẫn cache để nạp. Đừng suy luận chỉ từ tên option mà bỏ qua `AOTMode`.

### 6.3. Production: nạp cache

Chạy đúng JAR và cache đã tạo:

~~~bash
java \
  -XX:AOTMode=auto \
  -XX:AOTCache=build/aot/order-service.aot \
  -jar build/libs/order-service.jar
~~~

Ở chế độ `auto`, nếu cache tương thích, JVM dùng cache. Nếu không nạp được cache, ứng dụng vẫn tiếp tục chạy mà không dùng cache. Đây là lựa chọn phù hợp cho production khi tính sẵn sàng của ứng dụng quan trọng hơn việc bắt buộc cache phải nạp được.

### 6.4. Strict check trong CI

Để kiểm tra cache có thực sự tương thích, có thể dùng chế độ `on` trong bước validation:

~~~bash
java \
  -XX:AOTMode=on \
  -XX:AOTCache=build/aot/order-service.aot \
  -jar build/libs/order-service.jar \
  --smoke-test
~~~

Trong JDK 25, `on` là chế độ fail-fast: nếu không nạp được cache, JVM báo lỗi và thoát. Dùng nó trong CI hoặc môi trường kiểm thử tương thích; không mặc định biến một cache có thể thay đổi thành điều kiện bắt buộc duy nhất để production khởi động.

## 7. Chọn giữa AOTCacheOutput và AOTConfiguration

| Cách tạo | Lệnh chính | Khi phù hợp |
|---|---|---|
| Một bước thuận tiện | `-XX:AOTCacheOutput=app.aot` | Training tự kết thúc, muốn JVM tự chạy assembly |
| Tách record và create | `-XX:AOTConfiguration=app.aotconfig` rồi `AOTMode=create` | Service dài hạn, CI cần kiểm tra và lưu riêng từng artifact |
| Record đồng thời có config và cache output | `-XX:AOTConfiguration=app.aotconfig -XX:AOTCacheOutput=app.aot` | Muốn giữ dữ liệu training để audit/recreate, đồng thời tạo cache tự động khi record kết thúc |

Các option có ràng buộc:

- `-XX:AOTCache` và `-XX:AOTCacheOutput` không dùng cùng nhau trong một lệnh.
- `-XX:AOTConfiguration` là file cấu hình training; extension thông dụng là `.aotconfig`.
- `-XX:AOTCache` / `-XX:AOTCacheOutput` là đường dẫn cache; extension thông dụng là `.aot`.
- `AOTMode=record` cần ít nhất một trong hai option `AOTConfiguration` hoặc `AOTCacheOutput`.
- `AOTMode=create` cần `AOTConfiguration`; cache output có thể được chỉ định bằng `AOTCache`.
- Nếu dùng `AOTMode=auto` cùng `AOTConfiguration`, cần có `AOTCacheOutput` để JVM biết cache sẽ được tạo.

### JDK_AOT_VM_OPTIONS

Khi `record` với `AOTCacheOutput` tự khởi chạy JVM thứ hai để assembly, có thể truyền thêm JVM options cho tiến trình thứ hai qua biến môi trường `JDK_AOT_VM_OPTIONS`. Cú pháp định dạng giống `JAVA_TOOL_OPTIONS`.

Chỉ thêm tùy chọn khi thật sự cần đồng bộ môi trường của tiến trình assembly; trước khi dùng trong pipeline, kiểm tra tài liệu launcher của đúng bản JDK và bảo đảm không vô tình đưa option dành riêng cho training vào assembly.

## 8. Thiết kế workload training có tính đại diện

Cache chỉ hữu ích khi dữ liệu thu thập phản ánh các đường chạy quan trọng của ứng dụng. Một workload training tốt cần được thiết kế như một phần của pipeline, không phải thao tác thủ công ngẫu nhiên.

### Ví dụ workload cho dịch vụ Spring Boot

| Nhóm luồng | Hành động training | Mục đích |
|---|---|---|
| Startup | Khởi tạo context, component scan, cấu hình, serializer | Nạp các class nền tảng của ứng dụng |
| Authentication | Đăng nhập giả lập, kiểm tra token trong sandbox | Bao phủ code bảo mật và mapping |
| Read path | Đọc danh sách, truy vấn chi tiết, phân trang | Bao phủ repository, mapper, DTO |
| Write path | Tạo/cập nhật dữ liệu giả lập | Bao phủ validation, transaction, event |
| Integration | Gọi stub/mock server cho dependency ngoài | Bao phủ client và adapter |
| Error path | Request sai dữ liệu, timeout giả lập | Bao phủ nhánh lỗi quan trọng |

Không cần chạy toàn bộ test suite trong training. Chọn một workload ổn định, có thời lượng kiểm soát và tái hiện được. Các thao tác ghi nên dùng database test, schema dùng một lần hoặc transaction được rollback trong hệ thống kiểm thử.

### Độ phủ quan trọng hơn số lượng request

Chạy một triệu request chỉ vào endpoint health không đảm bảo cache tốt cho nghiệp vụ thanh toán. Ngược lại, một bộ workload ngắn nhưng đi qua các luồng startup, read/write và tích hợp trọng yếu có thể hữu ích hơn.

Hãy lưu cấu hình workload cùng version của ứng dụng để có thể tái tạo khi:

- Có dependency mới.
- Thay đổi framework hoặc serializer.
- Thêm module nghiệp vụ.
- Refactor đường khởi tạo.
- Thay đổi các option JVM ảnh hưởng khả năng tương thích.

### Tránh đưa trạng thái training vào production

Không nên để profile training tự động được kích hoạt trong production. Đặc biệt, không chạy các thao tác như tạo tài khoản thật, gửi email thật, thanh toán thật hoặc publish message thật chỉ để làm nóng cache.

Training là một môi trường có chủ đích; nó không phải bản sao production về dữ liệu và quyền truy cập.

## 9. Đóng gói cache cùng artifact ứng dụng

Một cache `.aot` phải được phân phối cùng đúng build ứng dụng mà nó được tạo ra. Cách đơn giản là lưu JAR và cache trong cùng thư mục release:

~~~text
release/
└── order-service/
    ├── app/
    │   └── order-service.jar
    ├── aot/
    │   ├── order-service.aotconfig
    │   └── order-service.aot
    └── manifest/
        └── aot-build-info.txt
~~~

Nội dung manifest ví dụ:

~~~text
application=order-service
application-version=2.7.4
artifact-sha256=<sha256-of-jar>
jdk-vendor=Eclipse Temurin
jdk-release=25.0.x
os=linux
architecture=x86_64
training-profile=aot-training
training-workload=checkout-readwrite-v3
cache-file=order-service.aot
~~~

Đây là metadata do pipeline tự ghi, không phải manifest format mà JVM yêu cầu. Mục tiêu là hỗ trợ truy vết và quyết định tái tạo cache.

### Pipeline gợi ý

~~~mermaid
flowchart TD
    A["Compile / package JAR"] --> B["Tính fingerprint artifact + JDK + OS/CPU"]
    B --> C["Chạy training workload"]
    C --> D["Tạo .aotconfig"]
    D --> E["Assembly tạo .aot"]
    E --> F["Smoke test với AOTMode=on"]
    F --> G{"Cache nạp thành công?"}
    G -->|Không| H["Đánh dấu build không đạt / điều tra"]
    G -->|Có| I["Đóng gói JAR + cache + manifest"]
    I --> J["Publish cùng release"]
    J --> K["Production dùng AOTMode=auto"]
~~~

Một build nên tạo cache một lần cho mỗi tổ hợp target. Nếu triển khai nhiều kiến trúc, hãy tạo cache riêng cho từng kiến trúc và môi trường tương ứng.

## 10. Quản lý tương thích khi nâng cấp ứng dụng hoặc JDK

Cache phải được tái tạo khi một trong các thành phần nhận dạng thay đổi.

| Thay đổi | Cần tạo lại cache? | Lý do |
|---|---|---|
| JAR ứng dụng đổi bytes | Có | Application artifact đã thay đổi |
| Dependency hoặc classpath đổi | Có | Tập lớp và cấu trúc ứng dụng thay đổi |
| Module path thay đổi | Có | Module graph/đầu vào ứng dụng thay đổi |
| JDK patch/release thay đổi | Có | Cache gắn với JDK release cụ thể |
| Chuyển Linux x86-64 sang ARM64 | Có | CPU architecture khác |
| Chuyển Linux sang Windows | Có | OS khác |
| Thay đổi JVM options | Cần kiểm tra tương thích; có thể phải tạo lại | Một số options không tương thích với cache |
| Chỉ đổi biến môi trường nghiệp vụ | Không nhất thiết | Nếu không làm thay đổi application identity hoặc option tương thích |
| Chỉ đổi dữ liệu runtime | Không nhất thiết | Cache không phải snapshot dữ liệu nghiệp vụ |

**Không nên tái sử dụng cache qua lần nâng JDK chỉ vì cả hai cùng major 25.** Tài liệu JDK 25 xác định cache gắn với JDK release; hãy tạo lại cache khi bản JDK chạy production thay đổi.

### Quy tắc cache key trong CI

Một khóa cache nội bộ có thể được tạo từ:

~~~text
aot-cache-key =
  application-artifact-hash
  + jdk-vendor-and-release
  + operating-system
  + cpu-architecture
  + launch-configuration-version
~~~

Có thể thêm hash của runtime options và dependency lock để giảm khả năng lấy nhầm cache. Đây là chính sách quản lý của pipeline, không phải công thức bắt buộc của HotSpot.

### Rollback release

Khi rollback, phải khôi phục **cặp JAR và cache cùng release**. Không lấy JAR của release cũ rồi dùng cache của release mới hoặc ngược lại.

Nếu cache không sẵn có, production có thể chạy bằng `AOTMode=auto` không cache. Điều này giúp ứng dụng duy trì khả năng khởi động trong khi pipeline tạo lại cache đúng phiên bản.

## 11. Production mode: auto, on và off

| Mode | Hành vi | Khi dùng |
|---|---|---|
| `auto` | Tự quyết định dùng cache nếu có thể; nếu không, tiếp tục chạy bình thường | Khuyến nghị cho production |
| `on` | Yêu cầu cache phải nạp được; lỗi thì JVM dừng | Kiểm tra tương thích/fail-fast |
| `off` | Không dùng AOT cache | Baseline so sánh hoặc tắt cache khi điều tra |
| `record` | Chạy training và ghi dữ liệu | Pipeline training |
| `create` | Assembly tạo cache từ config | Pipeline assembly |

### Lệnh production khuyến nghị

~~~bash
java \
  -XX:AOTMode=auto \
  -XX:AOTCache=/opt/order-service/aot/order-service.aot \
  -jar /opt/order-service/app/order-service.jar
~~~

Trong `auto`, nếu cache không tồn tại, không đọc được hoặc không tương thích, JVM tiếp tục chạy mà không dùng cache. Điều này giúp cache trở thành tối ưu hóa có thể bỏ qua thay vì điểm lỗi duy nhất của ứng dụng.

### Khi nào dùng on?

~~~bash
java \
  -XX:AOTMode=on \
  -XX:AOTCache=/opt/order-service/aot/order-service.aot \
  -jar /opt/order-service/app/order-service.jar
~~~

Dùng `on` trong CI hoặc kiểm thử trước release để xác nhận cache nạp được. Không dùng nó một cách vô điều kiện trên production nếu runtime có thể nhận JVM options từ agent, monitoring hoặc nền tảng triển khai mà pipeline không kiểm soát.

### Khi nào dùng off?

~~~bash
java -XX:AOTMode=off -jar order-service.jar
~~~

Dùng `off` để lấy baseline không AOT hoặc tạm thời loại trừ cache khi chẩn đoán sự cố. Khi so sánh hiệu năng, giữ các yếu tố khác như JDK, JVM options, tài nguyên CPU/memory và workload giống nhau.

## 12. Xác minh cache được sử dụng và chẩn đoán lỗi

### 12.1. Bật log AOT

Thêm unified logging:

~~~bash
java \
  -XX:AOTMode=auto \
  -XX:AOTCache=build/aot/order-service.aot \
  -Xlog:aot \
  -jar build/libs/order-service.jar
~~~

`-Xlog:aot` giúp quan sát quá trình nạp cache và lý do cache bị bỏ qua. Đọc log của đúng tiến trình production/test; không chỉ dựa vào việc file `.aot` tồn tại trên filesystem.

### 12.2. Kiểm tra file và metadata

Trước khi khởi động, xác nhận:

~~~bash
ls -lh build/aot/order-service.aot
ls -lh build/aot/order-service.aotconfig
sha256sum build/libs/order-service.jar
java --version
~~~

Trên Windows PowerShell:

~~~powershell
Get-Item .\build\aot\order-service.aot
Get-FileHash -Algorithm SHA256 .\build\libs\order-service.jar
java --version
~~~

Đối chiếu checksum JAR, JDK release và OS/CPU với manifest training. Không coi kích thước file khác 0 là bằng chứng cache tương thích.

### 12.3. Dùng jcmd

JDK 25 cung cấp lệnh `AOT.end_recording`:

~~~bash
jcmd -l
jcmd <PID> AOT.end_recording
~~~

Lệnh này kết thúc một AOT training đang diễn ra và ghi dữ liệu ra các file được chỉ định bởi `AOTConfiguration` và/hoặc `AOTCacheOutput`. Nó hữu ích khi training process là server chạy liên tục và cần dừng thu thập mà không thay đổi code ứng dụng.

### 12.4. Bảng xử lý sự cố

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `AOT cache file does not exist` | Sai đường dẫn hoặc pipeline chưa upload cache | Kiểm tra artifact path, quyền đọc và bước publish |
| Cache không được nạp nhưng app vẫn chạy | `AOTMode=auto` fallback hoặc cache không tương thích | Đọc `-Xlog:aot`, kiểm tra manifest |
| `AOTMode=on` làm JVM thoát | Cache không nạp được hoặc JVM options không tương thích | Dùng log để xác định nguyên nhân; tạo lại cache |
| Cache được tạo nhưng startup không cải thiện | Workload training chưa đại diện hoặc app không bị giới hạn bởi class loading | Đo lại startup/warm-up, cải thiện workload |
| Cache dùng được trên máy build nhưng không trên production | Khác JDK, OS/CPU, app artifact hoặc options | Tạo cache trong đúng target environment |
| Sau khi đổi dependency cache không còn dùng được | Classpath/application identity đã đổi | Build và training lại từ artifact mới |
| Training server không thoát | Service chạy lâu dài nên record chưa kết thúc | Dùng `jcmd <PID> AOT.end_recording` hoặc quy trình shutdown có kiểm soát |
| Assembly lỗi do thiếu config | Sai path hoặc record chưa hoàn thành | Kiểm tra `.aotconfig` và log training |
| Cache không nạp khi có agent/monitoring | JVMTI class-file load hook hoặc option chẩn đoán có thể không tương thích | Thử không agent để khoanh vùng; đánh giá options trong production |
| Khác module graph giữa training và production | Module options/classpath khác | Đồng bộ `--module-path`, `--add-modules` và các launch options |

Một số options như `--upgrade-module-path`, `--patch-module` hoặc `--limit-modules` có thể làm CDS bị vô hiệu hóa. Khi dùng các tùy chọn này, cần đọc log AOT/CDS thay vì giả định cache luôn được dùng.

## 13. Đo hiệu quả trước và sau khi dùng cache

AOT cache là tối ưu hóa hiệu năng, vì vậy pipeline nên có số liệu để quyết định có giữ cache hay không.

### Chỉ số cần theo dõi

| Chỉ số | Ý nghĩa |
|---|---|
| Process startup time | Thời gian từ lúc khởi chạy JVM tới mốc ứng dụng sẵn sàng |
| Time to first request | Thời gian tới request đầu tiên xử lý thành công |
| Warm-up latency | Độ trễ các request trong giai đoạn đầu |
| CPU trong startup | Chi phí CPU khi nạp, khởi tạo và liên kết |
| Memory footprint | Mức bộ nhớ sau khi ứng dụng ổn định |
| Cache load success rate | Tỷ lệ lần chạy nạp được AOT cache |
| Cache generation duration | Thời gian training/assembly trong pipeline |

### Quy trình benchmark

1. Chọn một JAR và workload cố định.
2. Chạy baseline với `-XX:AOTMode=off`.
3. Chạy với `-XX:AOTMode=auto` và cache tương thích.
4. Lặp lại đủ số lần trong cùng môi trường.
5. So sánh median và percentile của startup/first-request, đồng thời theo dõi CPU/memory.
6. Đảm bảo dữ liệu, trạng thái container, JVM options và cách đo giống nhau.
7. Chỉ đưa cache vào production khi lợi ích thực tế đáng kể và tỷ lệ nạp cache ổn định.

Ví dụ bảng kết quả để nhóm điền:

| Phiên bản thử | AOT mode | Startup median | First request p95 | CPU startup | Cache load |
|---|---|---:|---:|---:|---|
| Baseline | `off` | — | — | — | Không |
| Có cache | `auto` | — | — | — | Thành công |
| Có cache nhưng mismatch thử nghiệm | `auto` | — | — | — | Fallback |

Không so sánh một lần chạy duy nhất. Cache có thể giúp startup nhưng không cải thiện throughput của workload CPU-bound; cũng không thay thế việc tối ưu database, network hoặc thuật toán.

## 14. AOT cache và AOT Method Profiling trong Java 25

Java 25 có hai cải tiến AOT liên quan nhưng cần phân biệt:

- **JEP 514 — Ahead-of-Time Command-Line Ergonomics:** đơn giản hóa các lệnh record/create/use AOT cache. Đây là nội dung chính của bài.
- **JEP 515 — Ahead-of-Time Method Profiling:** giúp method-execution profiles từ lần chạy trước có sẵn khi HotSpot JVM khởi động, để JIT có thể bắt đầu tối ưu sớm hơn thay vì chờ thu thập profile trong lần chạy hiện tại.

JEP 515 là cải tiến về profile của phương thức; không nên tự suy luận rằng mọi nội dung profile được ghi vào `.aot` theo cùng cơ chế hoặc có thể dùng lệnh tạo cache ở bài này để kiểm soát toàn bộ method profiling.

Tài liệu launcher JDK 25 mô tả AOT cache hiện lưu Java classes và heap objects. Khi quản lý cache, hãy dựa vào hợp đồng được tài liệu JDK 25 công bố, không dựa vào dự đoán về các loại artifact có thể xuất hiện trong những bản JDK tương lai.

## 15. Checklist nghiệm thu pipeline

### Build và training

- [ ] JDK training là đúng JDK release mục tiêu production.
- [ ] JAR được build một lần và cùng artifact đó được dùng trong training, assembly và production.
- [ ] Workload đại diện cho startup, read/write và các luồng tích hợp quan trọng.
- [ ] Training chạy trong môi trường dữ liệu sandbox, không tạo side effect production.
- [ ] `.aotconfig` được ghi đầy đủ trước khi assembly.

### Assembly và kiểm tra

- [ ] `.aot` được tạo thành công.
- [ ] Assembly dùng đúng JAR, classpath/module-path, JDK và target OS/CPU.
- [ ] Smoke test với `AOTMode=on` nạp được cache.
- [ ] Log AOT không cho thấy cache bị bỏ qua ngoài ý muốn.
- [ ] Benchmark `off` và `auto` được thực hiện trong cùng điều kiện.

### Đóng gói và production

- [ ] JAR, `.aot` và manifest cùng thuộc một release.
- [ ] Cache key phản ánh application artifact, JDK release, OS/CPU và launch configuration.
- [ ] Cache được tái tạo khi một thành phần nhận dạng thay đổi.
- [ ] Production sử dụng `AOTMode=auto` để có fallback.
- [ ] Có phương án rollback đồng bộ JAR/cache.
- [ ] Có theo dõi tỷ lệ cache load và startup performance sau triển khai.

### Bài tập thực hành

Một dịch vụ `order-service` có JAR 2.7.4, chạy JDK 25 trên Linux x86-64. Hãy thiết kế pipeline:

1. Tạo `order-service.aotconfig` bằng workload training.
2. Dùng assembly tạo `order-service.aot`.
3. Kiểm tra cache bằng `AOTMode=on`.
4. Đóng gói cache và JAR vào cùng release.
5. Cấu hình production chạy `AOTMode=auto`.
6. Giải thích phải làm gì khi nâng JDK patch, thay dependency hoặc chuyển sang ARM64.

**Câu hỏi tự kiểm tra:**

1. Vì sao cache được tạo trên máy phát triển không nên mặc định đưa lên production?
2. Khi nào nên dùng `AOTCacheOutput` thay vì tách `AOTConfiguration` và `AOTCache`?
3. Vì sao training cần workload đại diện?
4. `AOTMode=auto` và `AOTMode=on` khác nhau thế nào khi cache không tương thích?
5. JEP 514 khác JEP 515 ở điểm nào?
6. Vì sao rollback phải khôi phục đúng cặp JAR và cache?

## 16. Tài liệu chính thức

- [JEP 483 — Ahead-of-Time Class Loading and Linking](https://openjdk.org/jeps/483): nền tảng AOT cache, training, consistency và các giới hạn tương thích.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): đơn giản hóa quy trình tạo và sử dụng AOT cache trong JDK 25.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): cải thiện startup bằng method-execution profiles có sẵn từ lần chạy trước.
- [Oracle JDK 25 — The java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): mô tả `AOTMode`, `AOTCache`, `AOTCacheOutput`, `AOTConfiguration`, compatibility và logging.
- [Oracle JDK 25 — The jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): lệnh `AOT.end_recording` để kết thúc training.
- [Oracle JDK 25 — Significant Changes](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): tổng quan các cải tiến AOT trong JDK 25.
- [Oracle JDK 25 — HotSpotAOTCacheMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/HotSpotAOTCacheMXBean.html): quản lý kết thúc AOT recording qua JMX.

> **Ghi nhớ:** Tạo AOT cache theo ba bước **training → assembly → production**. Gắn cache với đúng JAR, JDK release, OS và CPU; kiểm tra bằng `AOTMode=on` trong CI, còn production ưu tiên `AOTMode=auto` để ứng dụng vẫn chạy khi cache không tương thích.
