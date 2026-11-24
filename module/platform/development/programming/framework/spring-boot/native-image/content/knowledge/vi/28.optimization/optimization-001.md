# Đọc báo cáo build để tìm thành phần làm tăng kích thước hoặc thời gian biên dịch

## Mục tiêu bài học

Khi biên dịch Spring Boot thành **GraalVM Native Image**, thời gian build và kích thước executable có thể tăng đáng kể khi ứng dụng kéo theo nhiều dependency, nhiều method reachable, object được giữ trong image heap hoặc resource được đóng gói. Nếu chỉ nhìn tổng thời gian và kích thước file, bạn sẽ khó biết phần nào đang tạo ra chi phí.

Native Image cung cấp build output và, ở các bản phân phối hỗ trợ, **Build Report** dạng HTML để phân tích các thành phần của binary và những giai đoạn của quá trình biên dịch. Báo cáo giúp trả lời các câu hỏi như: package nào đóng góp nhiều code, object type nào chiếm image heap, resource nào được nhúng, build đang dành nhiều thời gian cho analysis hay compilation, và dependency nào cần được xem xét.

Bài học này giúp bạn:

- Bật Build Report và build output có cấu trúc.
- Đọc Summary, Code Area, Image Heap, Resources và SBOM.
- Phân biệt thành phần làm tăng kích thước binary với giai đoạn làm tăng thời gian build.
- Truy nguyên package, class, object và dependency gây chi phí.
- Chọn thay đổi tối ưu có mục tiêu và so sánh với baseline.
- Theo dõi xu hướng kích thước và thời gian build trong CI.

## 1. Vì sao cần đọc báo cáo build?

### 1.1. Tổng kích thước không chỉ là mã ứng dụng

Native executable có thể gồm nhiều thành phần:

- **Code area:** machine code được tạo cho các method reachable.
- **Image heap:** object và dữ liệu được giữ lại trong binary, gồm static state, metadata và dữ liệu resource.
- **Debug information:** thông tin phục vụ debug/profiling nếu được tạo hoặc nhúng.
- **Other data:** các dữ liệu và cấu trúc còn lại cần cho executable.

Một dependency có thể làm tăng code area vì nhiều method trở nên reachable. Dependency khác có thể làm tăng image heap do giữ nhiều object hoặc resource. Vì vậy, không thể kết luận chỉ từ số lượng JAR hoặc tổng số class.

### 1.2. Thời gian build cũng có nhiều nguồn

Native Image thực hiện phân tích reachability, xử lý metadata, tối ưu và biên dịch method, bố trí code rồi tạo binary. Thời gian có thể tăng vì:

- Dependency làm tập class, field và method reachable lớn hơn.
- Reflection, proxy hoặc metadata mở rộng tập thành phần phải giữ.
- Static initialization tạo object graph lớn trong build.
- Compiler phải tối ưu và biên dịch nhiều method.
- Máy build thiếu CPU hoặc memory, khiến GC và paging tăng.
- Debug information hoặc bước đóng gói/linking làm tăng thời gian tạo artifact.

**Kích thước binary và thời gian build là hai vấn đề liên quan nhưng không đồng nhất.** Một thay đổi có thể giảm code area nhưng không giảm thời gian analysis; một build chậm có thể do thiếu CPU/RAM dù binary cuối cùng không lớn.

### 1.3. Hai loại dữ liệu cần phân biệt

| Nguồn | Trả lời câu hỏi | Cách sử dụng |
|---|---|---|
| Build output trên terminal | Build đang đi qua phase nào, số liệu và tài nguyên tổng quát ra sao? | Tìm giai đoạn chậm và so sánh giữa các lần build |
| Build Report HTML | Thành phần nào đóng góp vào code area, image heap, resource và dependency inventory? | Drill-down tới package, class, object type và resource |
| Machine-readable build output JSON | Các số liệu build có cấu trúc để lưu và kiểm tra tự động là gì? | Theo dõi trend, đặt ngưỡng trong CI |

Build Report không thay thế log lỗi hoặc profiler của ứng dụng. Nó mô tả quá trình tạo native executable và nội dung binary.

## 2. Bật Build Report và build output

### 2.1. Tạo Build Report bằng native-image

Với GraalVM distribution hỗ trợ Build Report, thêm tùy chọn:

```bash
native-image --emit build-report -jar target/payment-service.jar
```

Có thể chỉ định đường dẫn report riêng:

```bash
native-image \
  --emit=build-report=reports/payment-service-build-report.html \
  -jar target/payment-service.jar
```

Sau khi build thành công, đường dẫn HTML report được liệt kê trong phần Build artifacts của output. Tên mặc định thường theo dạng `<binary-name>-build-report.html` và nằm cạnh binary.

**Lưu ý về edition:** theo tài liệu GraalVM hiện tại, HTML Build Report không có trong GraalVM Community Edition. Nếu `--emit build-report` không được hỗ trợ, hãy kiểm tra edition và version trước khi kết luận cấu hình build sai. Có thể dùng build output trên terminal và JSON output để theo dõi các số liệu mà toolchain cung cấp.

### 2.2. Bật qua Gradle Native Build Tools

Ví dụ cấu hình:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add("--emit=build-report")
            buildArgs.add(
                "-H:BuildOutputJSONFile=build/native/native-build-output.json"
            )
        }
    }
}
```

Tên task và cách cấu hình có thể khác theo phiên bản Gradle plugin. Đặt build arguments trong binary mà dự án thực sự dùng để tạo executable.

### 2.3. Bật qua Maven Native Build Tools

Ví dụ:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--emit=build-report</buildArg>
            <buildArg>-H:BuildOutputJSONFile=target/native-build-output.json</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Nếu dùng Spring Boot Maven plugin hoặc buildpack để tạo native image, truyền các arguments qua đúng plugin/builder đang thực hiện Native Image compilation. Không giả định cấu hình của `native-maven-plugin` tự áp dụng cho buildpack.

### 2.4. Kiểm tra tùy chọn của toolchain

Trước khi đưa arguments vào pipeline, xác nhận phiên bản và edition:

```bash
native-image --version
native-image --help
native-image --help-extra
```

Tên option, khả năng report và schema JSON có thể thay đổi giữa các phiên bản GraalVM. Dùng tài liệu tương ứng với toolchain của dự án; không sao chép nguyên xi option từ một phiên bản khác.

## 3. Đọc phần Summary

### 3.1. Environment

Summary thường hiển thị thông tin môi trường build, chẳng hạn:

- Java và GraalVM version.
- Cấu hình Graal compiler và optimization level.
- Target machine type/architecture.
- C compiler và phiên bản.
- Garbage collector được chọn cho executable.
- Các feature được người dùng hoặc framework bật.

Đây là phần đầu tiên cần kiểm tra khi so sánh hai báo cáo. Nếu GraalVM version, target architecture, optimization level hoặc feature khác nhau, chênh lệch kích thước/thời gian có thể đến từ môi trường thay vì source change.

### 3.2. Analysis Results

Phần này thể hiện kết quả points-to/reachability analysis, thường phân nhóm:

- Types.
- Fields.
- Methods.
- Thành phần reachable, reflection, JNI hoặc loaded theo cách report trình bày.

Số lượng lớn có thể gợi ý ứng dụng đang giữ một tập mã rộng, dùng nhiều reflection metadata hoặc có nhiều thư viện được nạp. Tuy nhiên, **số lượng method không bằng kích thước machine code** và cũng không trực tiếp cho biết thời gian biên dịch của từng dependency.

Hãy dùng số liệu này để nhận ra thay đổi bất thường giữa baseline và build mới, rồi drill-down trong Code Area hoặc kiểm tra dependency/metadata liên quan.

### 3.3. Image Details

Biểu đồ Image Details cho biết tỷ trọng của các phần như:

- Code area.
- Image heap.
- Debug information.
- Other data.

Chọn phần chiếm tỷ trọng lớn để điều tra tiếp. Nếu code area lớn, xem Code Area. Nếu image heap lớn, xem Image Heap và Resources. Nếu debug information lớn, xác nhận build có đang tạo/nhúng debug info theo yêu cầu hay không.

### 3.4. Resource Usage

Summary có thể cung cấp các số liệu tài nguyên của chính quá trình build:

- Thời gian tạo binary.
- Peak RSS của build process.
- CPU load.
- Garbage collection và các thống kê bộ nhớ liên quan.

Peak RSS cao cùng nhiều GC có thể cho thấy build process chịu áp lực memory. CPU load thấp trong khi tổng thời gian dài có thể gợi ý build bị giới hạn bởi memory, I/O hoặc chờ tài nguyên khác; cần đối chiếu với môi trường CI trước khi tăng số core.

Đây là số liệu của **Native Image build process**, không phải RSS hay GC behavior của ứng dụng native khi đang phục vụ request.

Tùy phiên bản, Summary còn có Security Report; report của build dùng Profile-Guided Optimization (PGO) có thể có thêm phần PGO Sampling Profile. Đây là thông tin bổ sung để review bảo mật hoặc profile tối ưu, không thay thế việc drill-down Code Area, Image Heap và Resources khi tìm nguyên nhân tăng kích thước.

## 4. Drill-down Code Area để tìm code làm binary lớn

### 4.1. Code Area chứa gì?

Code Area mô tả code được biên dịch từ các method reachable sau phân tích tĩnh. Build output có thể nhóm origin theo JAR, package hoặc class tùy thông tin sẵn có; Build Report cho phép xem sâu hơn theo package/class và method.

Trong report, có thể xem method-level breakdown, số lượng method và các thông tin kích thước/tỷ lệ mà phiên bản report cung cấp. Chọn một package để đi sâu vào package con và class; danh sách bên dưới được đồng bộ với biểu đồ.

### 4.2. Tìm dependency đóng góp nhiều code

Quy trình:

1. Mở Code Area và xem các origin/package chiếm tỷ lệ lớn.
2. Chọn package có tỷ lệ đáng chú ý để drill-down.
3. Xác định class và method đóng góp nhiều.
4. Đối chiếu package/class với dependency trong SBOM hoặc dependency tree của build tool.
5. Xác nhận thành phần đó thực sự được ứng dụng sử dụng.

Ví dụ, một thư viện reporting có thể kéo theo nhiều formatter, parser và font support dù service chỉ dùng một định dạng. Nếu phần lớn code của thư viện vẫn reachable, hãy xem có thể loại module không dùng, thay dependency nhẹ hơn hoặc chọn cấu hình tối giản được nhà cung cấp hỗ trợ hay không.

### 4.3. Không loại dependency chỉ vì tỷ lệ lớn

Một package chiếm tỷ lệ cao chưa chắc là phần thừa. Nó có thể cung cấp chức năng cốt lõi hoặc được nhiều luồng nghiệp vụ sử dụng.

Trước khi loại:

- Kiểm tra caller/use case và integration test.
- Xem dependency có được framework auto-configuration đăng ký không.
- Xác định có module tùy chọn hoặc starter kéo theo dependency không cần thiết.
- Kiểm tra reachability metadata có làm giữ thêm thành phần không cần không.
- Build lại và chạy toàn bộ native tests liên quan.

Mục tiêu là loại phần không cần thiết nhưng vẫn giữ đầy đủ hành vi sản phẩm.

### 4.4. Phân biệt số method và kích thước code

Một package có nhiều method nhỏ không nhất thiết chiếm nhiều code area hơn một package có ít method nhưng method phức tạp. Số lượng method reachable là chỉ số về phạm vi mã; kích thước code area là kết quả sau compiler và optimization.

So sánh nhiều build trong cùng toolchain, không dùng một ngưỡng số method chung cho mọi ứng dụng.

## 5. Đọc Image Heap để tìm object giữ trong binary

### 5.1. Image heap chứa gì?

Image heap lưu object được tạo và giữ lại trong quá trình Native Image build, ví dụ:

- Static data và object graph reachable.
- Metadata phục vụ runtime.
- Object được tạo bởi class initialization tại build time.
- Một số `byte[]` chứa dữ liệu, resource hoặc metadata.

Object graph lớn có thể làm binary tăng dù code area không đổi nhiều.

### 5.2. Tìm object type chiếm nhiều dung lượng

Image Heap thường nhóm theo object type và cung cấp:

- Số lượng instance.
- Tổng kích thước.
- Tỷ lệ so với image heap.

Sắp xếp theo size hoặc dùng tìm kiếm để kiểm tra class đáng chú ý. Ví dụ, nếu một class catalog có hàng trăm nghìn entry, hoặc một collection chứa nhiều chuỗi cấu hình, hãy xác định object graph đó được tạo ở đâu và có cần nằm trong image heap hay không.

### 5.3. Phân biệt object dữ liệu và resource

Một số resource được nhúng vào image dưới dạng `byte[]`. Report có thể hiển thị riêng resource trong tab Resources và cũng thể hiện đóng góp của dữ liệu resource trong image heap/build output.

Nếu image heap lớn, đừng chỉ tìm static collection trong code. Hãy kiểm tra resource lớn, reflection metadata, code metadata và các nhóm byte array mà build output phân loại.

### 5.4. Kiểm tra class initialization

Nếu class được khởi tạo ở build time, static initializer có thể tạo object graph được lưu trong image heap. Những class chứa cache, registry, locale data hoặc cấu hình lớn cần được kiểm tra:

- Dữ liệu có thực sự bất biến và cố định giữa các môi trường không?
- Có chứa thông tin chỉ phù hợp với máy build không?
- Có thể nạp dữ liệu ở runtime thay vì lưu snapshot trong binary không?
- Class có bị khởi tạo build time chỉ vì một dependency khác tham chiếu không?

Không chuyển hàng loạt class sang runtime initialization chỉ để giảm heap. Thay đổi class initialization có thể ảnh hưởng startup và tương thích; cần kiểm thử đúng class và luồng sử dụng.

## 6. Đọc Resources để tìm file được đóng gói ngoài ý muốn

### 6.1. Resources tab cho biết gì?

Resources tab liệt kê Java resources được đưa vào native image, cùng thông tin như tên, module/origin và kích thước. Report có thể phân biệt:

- Resource được yêu cầu rõ ràng qua metadata/configuration.
- Resource được framework đăng ký bằng API hints.
- Resource được yêu cầu nhưng không tìm thấy.
- Directory resource.

Các loại hiển thị cụ thể phụ thuộc phiên bản report.

### 6.2. Tìm resource lớn hoặc pattern quá rộng

Ví dụ, ứng dụng chỉ cần ba template email nhưng metadata đăng ký toàn bộ thư mục `templates/**`. Nếu thư mục có nhiều mẫu cũ, ảnh hoặc tài liệu, tất cả có thể được đóng gói vào binary.

Kiểm tra:

1. Sắp xếp resource theo kích thước.
2. Tìm file lớn hoặc nhóm resource cùng origin.
3. Xem resource được đăng ký bởi file metadata hay Runtime Hints nào.
4. Thu hẹp pattern tới tập file thật sự cần.
5. Chạy test trên native để xác nhận template/schema vẫn đọc được.

### 6.3. Missing resource không đồng nghĩa binary lớn

Resource được yêu cầu nhưng không tồn tại là vấn đề cấu hình hoặc build input. Nó có thể không làm binary lớn, nhưng có thể khiến ứng dụng lỗi khi runtime truy cập resource đó.

Xử lý missing resource bằng cách xác nhận file có được tạo/copy đúng lúc build, tên có phân biệt chữ hoa/chữ thường phù hợp với target filesystem, và pattern có khớp đường dẫn trong JAR không.

## 7. Dùng SBOM để liên hệ thành phần với dependency

### 7.1. SBOM cho biết những artifact nào tham gia build

Software Bill of Materials (SBOM) trong Build Report liệt kê các artifact cùng định danh và version được dùng để tạo binary. Đây là dữ liệu hữu ích để:

- Tìm dependency bất ngờ hoặc version không dự kiến.
- Đối chiếu origin trong Code Area với JAR/module tương ứng.
- Kiểm tra dependency bị kéo vào gián tiếp.
- Gắn kết quả benchmark với chính xác bộ dependency đã build.

SBOM không tự cho biết dependency nào gây ra bao nhiêu giây compilation. Hãy dùng nó để truy nguyên thành phần, rồi kết hợp phase timing và so sánh build.

### 7.2. Từ package tới dependency

Khi một package lớn xuất hiện trong Code Area:

1. Ghi lại package/class và origin hiển thị trong report.
2. Tìm artifact tương ứng trong SBOM.
3. Kiểm tra dependency tree của Maven hoặc Gradle để biết dependency trực tiếp/gián tiếp.
4. Xem starter hoặc module nào đưa artifact đó vào.
5. Tạo một build thử có thay đổi dependency/configuration duy nhất.
6. So sánh report và chạy lại test.

Không loại dependency chỉ bằng tên artifact; một số package có thể được shading/relocation hoặc chứa class dùng chung.

## 8. Tìm giai đoạn làm thời gian biên dịch tăng

### 8.1. Đọc các phase trong build output

Tên và cách hiển thị có thể khác giữa GraalVM versions, nhưng output thường cho thấy các giai đoạn như:

| Giai đoạn | Công việc | Dấu hiệu cần xem |
|---|---|---|
| Initializing | Khởi tạo Native Image builder và feature | Feature/plugin hoặc môi trường build |
| Analysis | Phân tích reachability và object graph | Types, fields, methods tăng bất thường |
| Inlining methods | Thực hiện inlining ở giai đoạn build | Thời gian và số vòng xử lý theo output |
| Compiling methods | Graal compiler biên dịch method reachable thành machine code | Số method và thời gian compile |
| Laying out methods | Sắp xếp/bố trí method đã biên dịch | Thời gian layout |
| Creating image | Tạo và ghi binary, xử lý link/debug artifacts | Thời gian tạo image và kích thước artifact |

Đừng chỉ nhìn tổng thời gian. Hãy xác định phase nào tăng so với baseline và thay đổi source/dependency nào xuất hiện cùng thời điểm.

### 8.2. Khi Analysis là phần chậm

Kiểm tra:

- Dependency hoặc starter mới làm tăng số type/method reachable.
- Reflection/proxy metadata có đăng ký quá rộng không.
- Feature hoặc auto-configuration nào đưa thêm graph vào build.
- Class initialization có tạo object graph lớn không.
- Có dependency/plugin nào chỉ cần ở một profile nhưng bị đưa vào mọi variant không.

Analysis chậm không nhất thiết do compiler tạo machine code chậm; đây là giai đoạn xác định tập thành phần có thể đi vào image.

### 8.3. Khi Compiling Methods là phần chậm

Kiểm tra:

- Số method reachable có tăng không?
- Một dependency có làm code area tăng đáng kể không?
- Optimization level có thay đổi không?
- Target machine type/architecture có giống baseline không?
- Máy build có đủ CPU và memory không?

Build output hiện đại có thể cung cấp thêm số liệu method/code area. Dùng Code Area để xác định package đóng góp nhiều code, nhưng không diễn giải tỷ lệ code area thành thời gian compile chính xác của package đó.

### 8.4. Khi Creating Image hoặc các phase cuối chậm

Kiểm tra image heap, resources, debug information, artifact linking và I/O của build workspace. Nếu output report cho thấy resource lớn hoặc image heap tăng, tìm nguyên nhân ở Resources/Image Heap. Nếu kích thước không đổi nhưng phase cuối chậm, kiểm tra CPU, disk, linker và cấu hình build environment.

### 8.5. Phân biệt giới hạn CPU và memory

Resource Usage giúp xem peak RSS, CPU load và GC của build process:

- Peak RSS gần memory limit cùng nhiều GC có thể báo hiệu thiếu memory.
- CPU load cao và nhiều method cần compile có thể cho thấy build CPU-bound.
- CPU load thấp cùng thời gian kéo dài có thể cần điều tra I/O, memory pressure hoặc giới hạn tài nguyên của CI.

Chỉ tăng CPU/RAM sau khi có bằng chứng. Tăng memory không giải quyết một dependency graph quá rộng; tăng CPU không sửa một build bị chờ I/O.

## 9. Dùng JSON để theo dõi build trong CI

### 9.1. Xuất machine-readable build output

Có thể yêu cầu builder tạo JSON:

```bash
native-image \
  -H:BuildOutputJSONFile=build/native/native-build-output.json \
  -jar target/payment-service.jar
```

JSON dành cho công cụ theo dõi tự động. Output trên terminal được thiết kế cho người đọc và có thể thay đổi theo version; không nên viết script parse log văn bản theo vị trí dòng hoặc regex mong manh.

JSON chỉ được tạo khi build thành công theo hành vi của builder. Hãy lưu schema tương ứng với phiên bản GraalVM và kiểm tra cấu trúc trước khi viết rule CI.

### 9.2. Theo dõi các ngưỡng có ý nghĩa

Có thể theo dõi:

- Tổng thời gian build.
- Peak RSS của build process.
- CPU load và GC statistics.
- Số method/type reachable.
- Tổng kích thước binary.
- Code area và image heap.
- Số lượng/kích thước resource.

Ví dụ, tài liệu GraalVM minh họa truy cập số method reachable trong JSON qua trường `analysis_results.methods.reachable`. Schema và tên trường có thể thay đổi; xác nhận JSON thực tế trước khi dùng path đó trong pipeline.

### 9.3. Đặt ngưỡng theo baseline

Không dùng một ngưỡng cứng chung cho mọi service. Lưu kết quả của một build chuẩn, sau đó đặt ngưỡng tăng tối đa có thể chấp nhận cho service đó.

Ví dụ chính sách:

- Cảnh báo khi tổng thời gian build tăng hơn mức baseline cho phép.
- Cảnh báo khi binary hoặc image heap tăng mạnh.
- Yêu cầu review khi số method reachable tăng đột biến.
- Theo dõi peak RSS để tránh CI runner bị OOM.

Ngưỡng nên tính đến dao động giữa các runner và toolchain. Dùng nhiều lần build để xác định baseline trước khi chặn pipeline.

## 10. Quy trình tối ưu dựa trên báo cáo

### Bước 1 — Lưu baseline

Build cùng source revision bằng toolchain mục tiêu. Lưu binary size, build output, Build Report nếu có, JSON output, GraalVM version, build args và thông tin runner.

### Bước 2 — Xác định phần chiếm nhiều nhất

Đọc Summary để biết tỷ lệ code area/image heap/debug/other. Drill-down Code Area, Image Heap, Resources và SBOM để tìm package, object type, resource hoặc dependency đáng chú ý.

### Bước 3 — Xác định phase chậm

Đọc build output và Resource Usage. Xác định Analysis, Compiling Methods, Creating Image hay môi trường CPU/memory/I/O là phần tăng thời gian.

### Bước 4 — Đưa ra giả thuyết cụ thể

Ví dụ:

- Một starter không cần thiết kéo theo nhiều method reachable.
- Một resource pattern quá rộng đóng gói nhiều file.
- Một class build-time initializer giữ object graph lớn.
- Một dependency mới làm tăng analysis và compile time.
- Runner CI thiếu memory khiến GC của builder tăng.

### Bước 5 — Thay đổi một yếu tố

Loại module thực sự không dùng, thu hẹp resource pattern, sửa cấu hình class initialization hoặc điều chỉnh tài nguyên build runner. Mỗi lần chỉ thay một nhóm nguyên nhân để biết tác động.

### Bước 6 — Build và so sánh lại

Dùng cùng GraalVM version, target, optimization level, CPU/memory và source baseline tương ứng. So sánh report trước/sau, chạy đầy đủ tests và kiểm tra hành vi native.

### Bước 7 — Lưu quyết định

Ghi rõ phần đã giảm, chỉ số nào thay đổi, chức năng nào được kiểm thử và trade-off nào phát sinh. Nếu kích thước giảm nhưng startup hoặc runtime latency xấu đi, cần đánh giá theo mục tiêu ban đầu.

## 11. Các tùy chọn tối ưu cần dùng có chủ đích

### 11.1. Chế độ build nhanh và tối ưu kích thước

Các GraalVM version hiện tại có thể cung cấp những optimization level như:

| Tùy chọn | Mục đích | Cách dùng |
|---|---|---|
| `-Ob` | Quick build mode, giúp giảm thời gian compilation | Phát triển/debug khi cần lặp build nhanh |
| `-O2` | Optimization level mặc định trong tài liệu hiện tại | Baseline theo cấu hình mặc định của toolchain |
| `-Os` | Tối ưu executable theo kích thước | Thử khi binary size là mục tiêu chính |

Các tùy chọn và mặc định phụ thuộc GraalVM version/distribution. `-Ob` có thể tạo binary với đặc tính runtime khác build tối ưu; không dùng kết quả quick build để kết luận hiệu năng production. Đo lại startup, throughput và latency khi thay optimization level.

### 11.2. Giảm phạm vi mã reachable

Các hướng có thể xem xét:

- Loại dependency hoặc module không dùng.
- Chọn starter/module nhỏ hơn nếu chức năng ứng dụng cho phép.
- Tránh đăng ký reflection/proxy/resource rộng hơn nhu cầu.
- Chỉ giữ resource cần thiết trong native image.
- Tránh khởi tạo build time những class tạo object graph lớn hoặc phụ thuộc môi trường.

Không xóa metadata chỉ để giảm số method. Metadata cần thiết bị loại có thể làm native executable lỗi ở một đường code ít được test.

### 11.3. Kiểm tra lại chức năng sau tối ưu

Sau mỗi thay đổi, chạy:

- Unit và integration tests.
- Spring AOT processing.
- Native compilation.
- Test các nhánh reflection, resource, proxy và serialization liên quan.
- Smoke test trên đúng OS/CPU/container target.
- Benchmark theo mục tiêu ban đầu.

Một binary nhỏ hơn nhưng thiếu resource hoặc mất implementation runtime không phải là tối ưu thành công.

## 12. Ví dụ đọc báo cáo

Giả sử một build mới có các dấu hiệu:

| Dấu hiệu | Giả thuyết cần kiểm tra | Bước tiếp theo |
|---|---|---|
| Code Area tăng mạnh sau khi thêm reporting starter | Starter kéo theo formatter/parser không dùng | Drill-down package và kiểm tra dependency tree |
| Image Heap tăng, có nhiều `byte[]` | Resource hoặc static object graph tăng | Mở Resources và Image Heap, kiểm tra class initialization |
| Resources tab có nhiều template cũ | Pattern đăng ký resource quá rộng | Thu hẹp Runtime Hints/resource configuration |
| Analysis phase tăng, method reachable tăng | Reachability graph rộng hơn | So sánh SBOM, metadata và auto-configuration |
| Compiling Methods tăng, code area cũng tăng | Compiler phải biên dịch nhiều method hơn | Drill-down Code Area và kiểm tra dependency mới |
| Peak RSS build process chạm giới hạn runner | Build bị memory pressure | Xem GC statistics và cấp runner phù hợp |
| Tổng build time tăng nhưng size gần như không đổi | Có thể do CPU/I/O hoặc phase không tạo thêm code | So sánh phase timing, CPU load và môi trường CI |

Các dấu hiệu trên là hướng điều tra, không phải kết luận tự động. Cần thay đổi một yếu tố và build lại để xác nhận nguyên nhân.

## 13. Checklist khi review Build Report

- GraalVM version, edition, JDK và target architecture có đúng baseline không?
- Optimization level và build arguments có giống lần so sánh trước không?
- Code area hay image heap là phần chiếm tỷ trọng lớn?
- Package/class nào đóng góp nhiều method hoặc code?
- Object type nào chiếm nhiều image heap?
- Có resource lớn, resource cũ hoặc pattern quá rộng không?
- Có missing resource cần xử lý không?
- SBOM có dependency mới hoặc version ngoài dự kiến không?
- Analysis hay Compiling Methods là phase tăng thời gian?
- Peak RSS, CPU load và GC cho thấy runner có thiếu tài nguyên không?
- Thay đổi tối ưu có giữ nguyên reflection, resource, proxy và serialization cần thiết không?
- Đã chạy lại native tests và benchmark sau tối ưu chưa?

### Câu hỏi tự kiểm tra

1. Code Area và Image Heap khác nhau như thế nào?
2. Vì sao số method reachable tăng không đồng nghĩa code area tăng theo cùng tỷ lệ?
3. Resources tab giúp phát hiện những vấn đề nào?
4. SBOM hỗ trợ truy nguyên dependency ra sao và vì sao nó không cho biết trực tiếp số giây compile của từng thư viện?
5. Nếu Analysis chậm nhưng Compiling Methods không tăng, nên kiểm tra những gì?
6. Peak RSS và CPU load của build process phản ánh điều gì?
7. Vì sao không nên parse build output văn bản để tạo rule CI?
8. Khi nào nên thử `-Ob` hoặc `-Os`, và cần đo lại những chỉ số nào?

## Tài liệu tham khảo

- [GraalVM Native Image Build Report](https://www.graalvm.org/latest/reference-manual/native-image/overview/build-report/)
- [GraalVM Native Image Build Output](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/)
- [GraalVM Native Image Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/)

**Ghi nhớ:** dùng Summary để xác định phần lớn và môi trường build; Code Area để truy nguyên method/package; Image Heap và Resources để tìm object/resource làm binary tăng; SBOM để đối chiếu dependency; build output và JSON để tìm phase chậm và theo dõi CI. Tối ưu theo một giả thuyết cụ thể, giữ baseline nhất quán và xác minh lại chức năng native sau mỗi thay đổi.
