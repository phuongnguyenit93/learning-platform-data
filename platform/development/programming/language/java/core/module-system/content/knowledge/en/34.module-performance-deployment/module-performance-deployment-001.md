# Chi phí resolve module graph lúc khởi động

## 1. Module resolution nằm ở đâu trong startup?

Khi chạy một ứng dụng modular, Java cần xây dựng **module graph** trước khi nạp main class và thực thi ứng dụng. Từ root module, resolver tìm các module cần thiết qua directive `requires`, kiểm tra quan hệ readability, tính nhất quán package và các ràng buộc của module system. Kết quả là một `Configuration` được dùng để tạo hoặc xác định module layer.

Đây là một phần của startup, nhưng không phải toàn bộ startup. Cần phân biệt:

1. **Module discovery và resolution:** tìm module trên module path, đọc metadata, giải quyết dependency và kiểm tra graph.
2. **Module layer creation:** tạo layer và class loader cho các module được resolve.
3. **Class loading và linking:** nạp, xác minh và liên kết class cần dùng.
4. **Service discovery và provider initialization:** tìm, khởi tạo provider khi ứng dụng duyệt `ServiceLoader`.
5. **Application initialization:** chạy static initializer, tạo object, mở kết nối, đọc cấu hình và thực hiện công việc của ứng dụng.

Nếu thời gian khởi động tăng, không nên mặc định nguyên nhân là module resolution. Một ứng dụng có graph nhỏ vẫn có thể startup chậm vì class loading, framework initialization, I/O hoặc kết nối bên ngoài.

## 2. Những yếu tố ảnh hưởng đến chi phí resolution

### Số lượng module có thể quan sát

Resolver cần tìm các module trong nguồn được cung cấp, chẳng hạn runtime image và module path. Module path chứa nhiều JAR hoặc thư mục module không liên quan có thể làm tăng công việc discovery và metadata inspection, tùy cách finder và filesystem hoạt động.

Giữ module path rõ ràng, chỉ chứa artifact cần cho runtime. Tránh đưa cả kho thư viện, thư mục build trung gian hoặc nhiều phiên bản dependency vào cùng module path.

### Độ rộng của dependency graph

Resolver bắt đầu từ root modules rồi lần theo dependency `requires`. Graph càng rộng hoặc sâu thì càng có nhiều module và quan hệ cần xử lý, kiểm tra.

Các nguyên nhân làm graph phình ra gồm:

- Thêm root module không cần thiết.
- Dùng `--add-modules ALL-MODULE-PATH` khiến nhiều module trên module path trở thành root.
- Dependency bắc cầu lớn hoặc một module facade truyền readability qua nhiều dependency.
- Các module provider và dependency của chúng được đưa vào graph qua service binding.
- Framework hoặc ứng dụng tạo nhiều module layer với các cấu hình riêng.

Số lượng JAR không phải thước đo duy nhất. Một module có nhiều dependency bắc cầu có thể tạo graph lớn hơn nhiều module nhỏ nhưng không được resolve.

### Service binding

Với configuration được tạo bằng `Configuration.resolveAndBind`, module system còn xét service type được các module trong graph khai báo qua `uses`, tìm module có `provides` phù hợp và bổ sung provider cùng dependency của chúng.

Điều này hữu ích cho SPI nhưng có thể làm graph rộng hơn. Một provider được thêm vào cũng có thể có dependency và service use riêng, khiến quá trình binding tiếp tục mở rộng graph.

Cần phân biệt việc đưa provider module vào graph với việc khởi tạo provider. Resolution/service binding xử lý module graph; `ServiceLoader` mới thực hiện việc tìm và khởi tạo implementation khi ứng dụng duyệt provider.

### Tạo module layer lặp lại

Một ứng dụng plugin có thể tạo custom `ModuleLayer` trong lúc chạy. Mỗi lần resolve configuration và define layer đều có chi phí riêng, ngoài chi phí boot layer ban đầu.

Nếu ứng dụng liên tục tạo layer giống nhau cho cùng một tập module, chi phí discovery, resolution, class loader và khởi tạo có thể lặp lại. Khi semantics và vòng đời cho phép, hãy tái sử dụng layer đã tạo thay vì xây lại cho mỗi request.

## 3. Đo startup trước khi tối ưu

Đo thời gian từ lúc tiến trình bắt đầu tới một mốc sẵn sàng có ý nghĩa với ứng dụng, chẳng hạn log `READY` sau khi hoàn tất khởi tạo cần thiết. Thời gian từ lúc gọi `java` tới khi main method bắt đầu không phản ánh đầy đủ thời điểm ứng dụng có thể phục vụ request.

Thiết kế phép đo:

- Dùng đúng JDK, JVM flags, module path, cấu hình và dữ liệu như môi trường mục tiêu.
- Chạy nhiều lần bằng tiến trình mới; ghi nhận median và p95 thay vì chỉ một lần.
- Tách cold start và warm filesystem cache nếu cả hai đều quan trọng.
- Giữ ổn định CPU, dung lượng heap, container limits và tải nền.
- Đo riêng thời điểm process start, main start và application ready nếu có thể.
- Không trộn thời gian build, tải artifact hoặc khởi tạo hạ tầng bên ngoài vào phép đo resolution nếu mục tiêu là hiểu riêng module graph.

Ví dụ trên Linux:

```bash
/usr/bin/time -f 'elapsed=%e s' \\
  java --module-path mods \\
  -m com.acme.app/com.acme.app.Main
```

Trên PowerShell:

```powershell
Measure-Command {
    java --module-path mods -m com.acme.app/com.acme.app.Main
}
```

Các lệnh này đo thời gian tổng của process. Để đo thời điểm application ready, nên để ứng dụng phát một mốc log/metric rõ ràng và dùng harness bên ngoài ghi thời gian từ khi khởi chạy tới mốc đó.

Không so sánh hai cấu hình nếu một cấu hình bật log debug, JFR hoặc in module resolution còn cấu hình kia không bật. Công cụ chẩn đoán có thể tạo thêm I/O và overhead.

## 4. Quan sát module graph thực tế

Bật `--show-module-resolution` để xem module nào được chọn làm root, module nào được resolve qua `requires` và module nào được bind qua service:

```bash
java --show-module-resolution \\
  --module-path mods \\
  -m com.acme.app/com.acme.app.Main
```

Đầu ra minh họa:

```text
root com.acme.app file:///opt/app/mods/com.acme.app.jar
com.acme.app requires com.acme.api file:///opt/app/mods/com.acme.api.jar
com.acme.api requires java.logging jrt:/java.logging
com.acme.app binds com.acme.provider.json file:///opt/app/mods/com.acme.provider.json.jar
```

Cách đọc:

- `root`: module được chọn làm điểm bắt đầu của resolution.
- `requires`: dependency được đưa vào graph theo module descriptor.
- `binds`: provider module được bổ sung qua service binding.

Output này giúp nhận diện module không mong muốn, dependency bắc cầu lớn và provider được bind. Nó không phải báo cáo thời gian cho từng bước resolution; không thể nhìn một dòng `binds` rồi kết luận provider đó tốn bao nhiêu mili giây.

Có thể dùng `--list-modules` để xem module mà launcher có thể liệt kê trong cấu hình hiện tại:

```bash
java --module-path mods --list-modules
```

Đây là danh sách module có thể quan sát, không đồng nghĩa tất cả module đều được resolve vào graph của ứng dụng.

## 5. Dùng jdeps để giảm dependency không cần thiết

`jdeps` phân tích dependency tĩnh của class files và JAR. Nó giúp hiểu vì sao module graph cần các module nhất định và phát hiện dependency không còn cần thiết.

Tóm tắt dependency:

```bash
jdeps --module-path mods --summary mods/com.acme.app.jar
```

Liệt kê module dependency:

```bash
jdeps --module-path mods --list-deps mods/com.acme.app.jar
```

In danh sách tên module phân tách bằng dấu phẩy:

```bash
jdeps --module-path mods \\
  --print-module-deps mods/com.acme.app.jar
```

Kiểm tra descriptor:

```bash
jdeps --module-path mods --check com.acme.app
```

Các kết quả giúp tìm dependency tĩnh không cần thiết hoặc module descriptor quá rộng. Tuy nhiên, jdeps không thể luôn phát hiện class được nạp qua reflection, tên class trong cấu hình, plugin động hoặc mọi service provider. Không xóa `uses`, `provides` hay dependency chỉ vì chúng không xuất hiện trong báo cáo bytecode.

## 6. Tối ưu module path và root modules

### Chỉ đưa dependency cần thiết vào module path

Tổ chức thư mục runtime riêng, chứa đúng phiên bản JAR được triển khai. Không dùng một thư mục chung có nhiều phiên bản hoặc artifact build thử nghiệm.

Ví dụ:

```text
runtime/
├── app/
│   └── com.acme.app.jar
└── mods/
    ├── com.acme.api.jar
    ├── com.acme.spi.jar
    └── com.acme.provider.json.jar
```

Giữ module path ổn định giữa các môi trường để tránh resolution phải xử lý tập artifact khác nhau và giảm lỗi do trùng tên module.

### Tránh thêm tất cả module làm root khi không cần

`--add-modules ALL-MODULE-PATH` có thể hữu ích cho kiểm tra hoặc một số môi trường plugin, nhưng biến tất cả module trên module path thành root có thể mở rộng graph đáng kể.

Trong production, chỉ thêm các root module thực sự cần. Module cần thiết qua `requires` sẽ được resolver tìm theo dependency closure.

### Duy trì dependency rõ ràng

Ưu tiên module descriptor thể hiện dependency thực tế. Tránh thêm `requires transitive` nếu API công khai không cần truyền readability cho consumer. Dependency bắc cầu rộng có thể làm các module phía sau phải đọc thêm module không cần thiết.

Automatic module hữu ích trong giai đoạn chuyển đổi, nhưng explicit module descriptor giúp kiểm soát rõ hơn `requires`, `exports`, `uses` và `provides`. Việc chuyển sang explicit module không bảo đảm tự động nhanh hơn; lợi ích chính là graph và API boundary rõ ràng hơn.

## 7. Kiểm soát service binding và provider

Nếu ứng dụng sử dụng SPI, kiểm tra provider nào thực sự cần được đưa vào runtime. Không để module path chứa nhiều provider thử nghiệm hoặc plugin không được sử dụng.

Với `jlink`, tùy chọn `--bind-services` yêu cầu linker liên kết service provider cùng dependency của chúng. Điều này có thể làm runtime image chứa thêm module provider. Chỉ bật khi ứng dụng cần các provider đó.

Ví dụ:

```bash
jlink \\
  --module-path "$JAVA_HOME/jmods:mods" \\
  --add-modules com.acme.app \\
  --bind-services \\
  --output runtime-image
```

Nếu không cần tất cả provider có thể quan sát, hãy xem xét tập module và service mà ứng dụng thực sự sử dụng trước khi bật service binding trong image. Cần kiểm thử để bảo đảm không vô tình loại provider cần thiết.

Ở runtime, tránh tạo nhiều custom layer hoặc duyệt và khởi tạo tất cả provider khi chỉ cần một implementation. Nếu service cần một provider được cấu hình rõ ràng, áp dụng chính sách lựa chọn phù hợp thay vì phụ thuộc vào thứ tự duyệt.

## 8. Dùng jlink để tạo runtime image gọn

`jlink` tạo runtime image chứa tập module được chọn và dependency cần thiết. Image nhỏ hơn có thể giảm lượng module hệ thống cần triển khai và giúp môi trường runtime ổn định hơn.

Ví dụ cơ bản:

```bash
jlink \\
  --module-path "$JAVA_HOME/jmods:mods" \\
  --add-modules com.acme.app \\
  --output runtime-image
```

Chạy bằng image:

```bash
runtime-image/bin/java \\
  --module-path mods \\
  -m com.acme.app/com.acme.app.Main
```

Trên Windows, executable là `runtime-image\\bin\\java.exe` và dấu phân cách các entry trong module path là dấu chấm phẩy.

`jlink` thực hiện phần lớn công việc lựa chọn module ở build time và tạo runtime image tùy biến. Nó không loại bỏ mọi chi phí resolution của ứng dụng khi khởi chạy, vì application modules và layer vẫn cần được xử lý. Tác động thực tế tới startup phụ thuộc vào kích thước image, module graph, filesystem và cách ứng dụng chạy.

Dùng `jdeps --print-module-deps` để hỗ trợ xác định dependency tĩnh, nhưng bổ sung module được dùng qua reflection, service binding hoặc cấu hình động trước khi link image. Kiểm thử image bằng các luồng chức năng thực tế.

## 9. Phân biệt resolution với class loading và CDS

Nếu startup chậm, có thể phần tốn thời gian nằm sau module resolution:

- Class loading và verification của nhiều class.
- Static initializer chạy nhiều công việc.
- Framework scan classpath/module path hoặc annotation.
- Khởi tạo logging, dependency injection và serializer.
- Kết nối database, DNS, TLS hoặc remote service.
- JIT compilation và warm-up của code.

Class Data Sharing (CDS) có thể giảm một phần chi phí khởi tạo JVM và nạp class bằng cách chia sẻ metadata/class data đã được archive. CDS không thay thế module resolution và không làm dependency graph biến mất.

Khi thử CDS, đo riêng cấu hình có và không có archive, giữ các yếu tố khác giống nhau. Không kết luận module resolution đã nhanh hơn chỉ từ việc tổng startup giảm; mức giảm có thể đến từ class loading hoặc các phần khác.

## 10. Đo và so sánh từng thay đổi

Nên thay đổi từng yếu tố để biết tác động:

| Thí nghiệm | Điều cần giữ cố định | Điều cần quan sát |
|---|---|---|
| Giảm số JAR trên module path | JDK, root, application code | Discovery và tổng startup |
| Bỏ root không cần thiết | Module path và service behavior | Kích thước graph, startup |
| Giảm dependency bắc cầu | API behavior và test | Module được resolve và compatibility |
| Giảm provider được bind | Service contract và output | Số provider/module trong graph |
| Tái sử dụng custom layer | Plugin lifecycle và semantics | Thời gian tạo layer, startup/request latency |
| Dùng jlink image | JDK version và chức năng | Image size, startup, deployment behavior |
| Bật CDS | Cùng module graph và workload | Class loading và tổng startup |

Mỗi cấu hình nên được chạy nhiều lần trong tiến trình mới. Ghi lại JDK vendor/version, OS, CPU, container memory/CPU limits, module path, JVM flags, số module resolve và mốc application ready.

Dùng median và p95 để tránh kết luận từ một lần chạy bất thường. Nếu chỉ đo tổng startup, hãy gọi kết quả là tổng startup; không gán toàn bộ chênh lệch cho module resolution nếu chưa có bằng chứng.

## 11. Những sai lầm khi tối ưu

- **Bật `--limit-modules` chỉ để mong startup nhanh hơn:** tùy chọn này thay đổi universe module observable và có thể làm thiếu dependency hoặc provider. Nó không phải nút tăng tốc chung; chỉ dùng khi tập module được giới hạn đã được xác định và kiểm thử.
- **Dùng `ALL-MODULE-PATH` trong production mà không cần:** tùy chọn này có thể mở rộng tập root và graph.
- **Xóa module theo output của jdeps mà không kiểm tra reflection/SPI:** có thể làm plugin hoặc provider biến mất.
- **Tạo layer mới cho mỗi request:** làm lặp lại chi phí resolve và define layer.
- **Bật log chẩn đoán trong benchmark:** output console có thể làm sai lệch số đo.
- **Cho rằng jlink loại bỏ hoàn toàn resolution:** image nhỏ hơn nhưng ứng dụng vẫn cần khởi tạo module graph/layer cần thiết.
- **Tối ưu số module mà bỏ qua initialization:** framework scan, I/O và static initializer thường có thể chiếm phần đáng kể của startup.

## 12. Quy trình tối ưu thực tế

1. Đo baseline từ process start tới application ready với cấu hình production.
2. Chạy lại với `--show-module-resolution` để hiểu root, dependency và service binding.
3. Dùng `jdeps` để tìm dependency tĩnh không cần thiết và kiểm tra descriptor.
4. Kiểm tra module path, root modules và provider có được đưa vào graph đúng nhu cầu không.
5. Xem có custom layer hoặc service provider nào bị khởi tạo lặp lại không.
6. Nếu runtime image lớn, thử `jlink` với tập module đã xác định và test đầy đủ.
7. Phân tích class loading, framework initialization và I/O nếu tổng startup vẫn chậm.
8. Chạy lại cùng benchmark và so sánh median/p95 trước khi chấp nhận thay đổi.

## Ghi nhớ

- Module resolution là một phần startup, tách biệt với layer creation, class loading, provider initialization và application initialization.
- Chi phí phụ thuộc vào module discovery, độ rộng dependency graph, service binding và số custom layer được tạo.
- `--show-module-resolution` giúp quan sát graph nhưng không đo thời gian cho từng bước.
- `jdeps` giúp giảm dependency tĩnh; phải bổ sung các dependency động và service.
- Giữ module path nhỏ, root rõ ràng, provider cần thiết và tái sử dụng layer khi phù hợp.
- `jlink` và CDS có thể giảm các phần chi phí khác nhau; đo riêng để xác định hiệu quả thực tế.
- Không gán mọi cải thiện startup cho module resolution nếu phép đo chưa tách được các giai đoạn.
