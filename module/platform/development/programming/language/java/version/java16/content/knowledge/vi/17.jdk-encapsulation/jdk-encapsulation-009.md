# Dùng jdeps --jdk-internals để tìm phụ thuộc tĩnh vào API nội bộ

`jdeps` là công cụ phân tích dependency đi kèm JDK. Tùy chọn `--jdk-internals` tìm các tham chiếu ở cấp lớp tới API nội bộ của JDK trong bytecode đã biên dịch. Công cụ giúp phát hiện những dependency có thể bị chặn bởi strong encapsulation hoặc thay đổi không tương thích khi nâng cấp JDK.

Phân tích này hữu ích khi kiểm tra ứng dụng và thư viện trước khi chuyển sang Java 16 hoặc JDK mới hơn. Java 16 đặt strong encapsulation làm mặc định theo JEP 396; Java 17 tiếp tục hoàn tất quá trình này theo JEP 403. Vì vậy, hãy kiểm tra artifact đã build và các thư viện đi kèm thay vì chỉ tìm tên package trong source code.

`jdeps` là phân tích tĩnh. Nó tìm dependency thể hiện trong class file, nhưng không phát hiện đầy đủ truy cập được tạo động qua reflection, tên lớp dạng chuỗi hoặc cơ chế nạp lớp lúc runtime. Cần kết hợp kết quả với kiểm thử ứng dụng và rà soát cấu hình framework.

## 1. JDK internal API là gì?

JDK chứa cả API công khai của Java SE lẫn các lớp phục vụ implementation nội bộ. API công khai được tài liệu hóa và có cam kết tương thích theo chính sách của nền tảng. Internal API là chi tiết triển khai hoặc API không được công bố như một phần ổn định mà ứng dụng nên phụ thuộc.

Một số package có tên như `sun.*` hoặc `com.sun.*` thường là dấu hiệu cần kiểm tra. Tuy nhiên, không nên chỉ dựa vào tiền tố package để kết luận. Hãy xem tài liệu API, module chứa package và trạng thái export của nó.

Ví dụ một thư viện cũ có thể gọi trực tiếp:

```java
import sun.misc.BASE64Encoder;

String encoded = new BASE64Encoder().encode(data);
```

`sun.misc.BASE64Encoder` là JDK internal API, không phải API Java SE để ứng dụng mới dựa vào. Java đã cung cấp `java.util.Base64` từ Java 8:

```java
import java.util.Base64;

String encoded = Base64.getEncoder().encodeToString(data);
```

Khi thay thế dependency nội bộ bằng API công khai, ứng dụng giảm rủi ro khi nâng cấp JDK và không cần dựa vào các tùy chọn mở quyền truy cập nội bộ.

## 2. jdeps --jdk-internals kiểm tra điều gì?

Lệnh `jdeps --jdk-internals` tìm **class-level dependencies** tới JDK internal APIs trong các file class được phân tích. Các dependency này có thể xuất hiện do mã nguồn tham chiếu trực tiếp một lớp nội bộ rồi được biên dịch thành bytecode.

Công cụ nhận các đầu vào như:

- File `.class`.
- Thư mục chứa các file class.
- File JAR.
- Tên lớp đầy đủ để phân tích class tương ứng.

Tùy chọn `--jdk-internals` yêu cầu `jdeps` tập trung vào dependency tới API nội bộ của JDK. Kết quả có thể chỉ ra lớp ứng dụng đang tham chiếu API nào và gợi ý API thay thế nếu công cụ có dữ liệu tương ứng.

Ví dụ đơn giản:

```bash
jdeps --jdk-internals build/libs/service.jar
```

Trên Windows PowerShell, nếu đang ở thư mục gốc dự án:

```powershell
jdeps --jdk-internals .\build\libs\service.jar
```

Nếu `jdeps` không nằm trong PATH, gọi trực tiếp công cụ thuộc JDK đang dùng:

```powershell
& "$env:JAVA_HOME\bin\jdeps.exe" --jdk-internals .\build\libs\service.jar
```

Hãy dùng `jdeps` từ JDK mục tiêu mà ứng dụng sẽ chạy, hoặc ghi rõ phiên bản JDK của công cụ trong báo cáo phân tích. Có thể kiểm tra phiên bản bằng:

```bash
jdeps --version
```

## 3. Đọc kết quả phân tích

Khi phát hiện dependency nội bộ, `jdeps` thường hiển thị artifact hoặc lớp nguồn, API nội bộ được tham chiếu và cảnh báo rằng internal API không được hỗ trợ ổn định. Nếu có thể nhận diện giải pháp thay thế, kết quả có thể kèm cột gợi ý.

Ví dụ minh họa dạng output:

```text
Sample.class -> JDK removed internal API
   Sample -> sun.misc.BASE64Encoder  JDK internal API (JDK removed internal API)

Warning: JDK internal APIs are unsupported and private to JDK implementation
that are subject to be removed or changed incompatibly and could break your application.

JDK Internal API                 Suggested Replacement
----------------                 ---------------------
sun.misc.BASE64Encoder           Use java.util.Base64 @since 1.8
```

Đây là output minh họa dựa trên định dạng ví dụ trong tài liệu migration của Oracle. Nội dung và cách phân loại cụ thể có thể thay đổi theo phiên bản JDK và API được phát hiện.

Cách đọc:

- `Sample.class` là lớp có dependency.
- `sun.misc.BASE64Encoder` là internal API được tham chiếu.
- `JDK removed internal API` cho biết API đó đã bị loại khỏi JDK mục tiêu hoặc không còn được cung cấp như trước.
- `Suggested Replacement` đưa ra gợi ý khi công cụ biết API công khai phù hợp.

Không phải mọi internal API đều có một thay thế tương đương. Với những trường hợp không có gợi ý, cần đọc tài liệu API và xác định lại mục đích mà mã cũ đang thực hiện.

## 4. Quét JAR của ứng dụng

Trong pipeline build, hãy chạy phân tích sau khi tạo artifact. Ví dụ với JAR được đóng gói vào thư mục `build/libs`:

```bash
jdeps --jdk-internals build/libs/service.jar
```

Nếu dự án tạo nhiều JAR, có thể truyền nhiều artifact trong cùng một lần chạy:

```bash
jdeps --jdk-internals build/libs/service.jar build/libs/worker.jar
```

Điều này giúp kiểm tra các module hoặc ứng dụng được đóng gói riêng. Tuy nhiên, phải chắc rằng tất cả artifact cần kiểm tra đã được đưa vào danh sách đầu vào.

Không chỉ phân tích source code hoặc thư mục build tạm. Dependency thực tế nằm trong bytecode sau compile; đó là thứ sẽ được triển khai và nạp bởi JVM.

## 5. Đưa dependency bên ngoài vào class path

Ứng dụng thường phụ thuộc vào nhiều thư viện JAR. Nếu chỉ phân tích JAR ứng dụng mà không đưa các thư viện liên quan vào phạm vi phân tích, kết quả có thể bỏ sót internal API được gọi từ dependency.

Dùng `--class-path` để chỉ ra các lớp và JAR cần thiết:

```bash
jdeps --jdk-internals --class-path "lib/codec.jar:lib/legacy-client.jar" build/libs/service.jar
```

Trên Windows, dấu phân cách giữa các mục class path là dấu chấm phẩy:

```powershell
jdeps --jdk-internals --class-path "lib\codec.jar;lib\legacy-client.jar" .\build\libs\service.jar
```

Theo tài liệu `jdeps`, khi dùng `--jdk-internals`, công cụ mặc định phân tích các lớp trong các file đầu vào và các lớp được chỉ định trong `--class-path`, trừ khi có bộ lọc `-include`. Vì vậy, hãy đưa đầy đủ thư viện cần rà soát vào class path.

Nếu dự án dùng module path, dùng `--module-path` để chỉ ra vị trí các module phụ thuộc. Đừng nhầm class path với module path: chúng biểu diễn hai cách phân giải module/lớp khác nhau trong ứng dụng Java.

## 6. Phân tích thư viện trên module path

Với ứng dụng modular, có thể chỉ rõ module path:

```bash
jdeps --jdk-internals --module-path "mods;lib" app.jar
```

Ví dụ trên dùng dấu phân cách Windows. Trên Linux và macOS, các mục module path được phân cách bằng dấu hai chấm:

```bash
jdeps --jdk-internals --module-path "mods:lib" app.jar
```

Cấu trúc thư mục thực tế phụ thuộc cách build và đóng gói module. Nếu ứng dụng có cả module path lẫn class path, khai báo từng loại theo đúng vị trí artifact.

Nếu thiếu dependency hoặc module không được phân giải, xử lý class path/module path trước khi kết luận rằng không có internal API. Một báo cáo phân tích không đầy đủ không chứng minh artifact độc lập với JDK internals.

## 7. Multi-release JAR và phiên bản bytecode được phân tích

Một multi-release JAR có thể chứa nhiều phiên bản class cho các phiên bản Java khác nhau. Khi phân tích loại JAR này, dùng `--multi-release` để chọn phiên bản cần kiểm tra.

Ví dụ phân tích phần class dành cho Java 17:

```bash
jdeps --jdk-internals --multi-release 17 build/libs/multi-release-library.jar
```

Có thể chọn phần base của JAR:

```bash
jdeps --jdk-internals --multi-release base build/libs/multi-release-library.jar
```

Giá trị phiên bản phải là số nguyên từ 9 trở lên hoặc `base`. Chọn phiên bản tương ứng với runtime mà ứng dụng hỗ trợ. Nếu thư viện có các implementation riêng theo phiên bản Java, nên kiểm tra từng target runtime được triển khai.

Không nên chỉ quét phần base rồi kết luận toàn bộ multi-release JAR không dùng internal API. Một lớp nằm trong thư mục phiên bản cao hơn có thể có dependency khác.

## 8. Tìm dependency trong toàn bộ cây thư viện

Trong dự án lớn, internal API có thể xuất hiện ở dependency bậc sâu thay vì mã ứng dụng. Cần lập danh sách artifact thực tế được đóng gói hoặc nạp trong môi trường triển khai.

Quy trình đề xuất:

1. Lấy danh sách JAR/module từ dependency report của build tool.
2. Xác định thư viện được đóng gói trong artifact và thư viện được cung cấp ở runtime.
3. Chạy `jdeps --jdk-internals` trên JAR ứng dụng.
4. Đưa các JAR phụ thuộc cần rà soát vào `--class-path` hoặc `--module-path`.
5. Với multi-release JAR, chọn target bằng `--multi-release`.
6. Lưu output để đối chiếu sau khi nâng cấp thư viện.

Không phải dependency nào trong máy phát triển cũng được đóng gói vào production. Ngược lại, một container hoặc application server có thể cung cấp thư viện ở runtime mà không nằm trong artifact ứng dụng. Phạm vi quét phải khớp với cách ứng dụng được triển khai.

## 9. jdeps không phát hiện mọi truy cập nội bộ

`jdeps` phân tích bytecode và dependency tĩnh. Công cụ không thể đảm bảo phát hiện mọi trường hợp mã chỉ ra lớp nội bộ bằng tên chuỗi rồi tải lúc runtime.

Ví dụ:

```java
String className = configuration.getProperty("implementation.class");
Class<?> implementation = Class.forName(className);
```

Nếu giá trị cấu hình là tên một JDK internal class, tham chiếu đó không nhất thiết xuất hiện như dependency lớp trực tiếp trong bytecode. `jdeps` có thể không nhận diện được lớp đích từ chuỗi cấu hình.

Các trường hợp cần rà soát bổ sung:

- `Class.forName("...")` với tên lớp lấy từ cấu hình.
- `ClassLoader.loadClass(...)` với tên lớp tạo động.
- Reflection tìm field hoặc method bằng tên chuỗi.
- Framework dùng metadata hoặc annotation để truy cập sâu vào lớp.
- Service loader hoặc plugin nạp implementation từ runtime environment.
- Bytecode được tạo hoặc biến đổi động trong quá trình chạy.

Vì vậy, kết quả không có cảnh báo chỉ có nghĩa là công cụ không tìm thấy dependency tĩnh trong phạm vi đã quét. Nó không phải bằng chứng tuyệt đối rằng ứng dụng không truy cập JDK internals.

## 10. Kết hợp jdeps với kiểm thử runtime

Để kiểm tra cả dependency tĩnh và hành vi thực tế:

- Chạy `jdeps --jdk-internals` trên artifact và các dependency liên quan.
- Kiểm thử các luồng ứng dụng sử dụng reflection hoặc framework serialization.
- Chạy integration test trên đúng JDK production.
- Đọc stack trace khi gặp `IllegalAccessError` hoặc `InaccessibleObjectException`.
- Kiểm tra cấu hình framework, plugin và tên lớp nạp động.

Trong quá trình di trú Java 16, tùy chọn `--illegal-access=deny` từng được dùng để xác nhận ứng dụng không còn dựa vào một số quyền truy cập reflection tương thích cũ. Đây là ngữ cảnh lịch sử của quá trình chuyển đổi. Từ Java 17, `--illegal-access` không còn mở lại package theo cách cũ và không nên được dùng làm giải pháp cho runtime hiện đại.

Nếu framework vẫn cần deep reflection vào một package cụ thể, xác định đúng module/package và cân nhắc `--add-opens` có phạm vi hẹp trong thời gian chuyển tiếp. Nếu bytecode tham chiếu trực tiếp một internal API, `--add-opens` không giải quyết dependency tĩnh đó; cần API công khai hoặc một giải pháp tương thích cụ thể, có kiểm soát.

## 11. Phân biệt jdeps --jdk-internals với các tùy chọn jdeps khác

`jdeps` có nhiều chế độ phân tích dependency. Không phải tùy chọn nào cũng trả lời câu hỏi về JDK internal APIs.

| Tùy chọn | Mục đích |
|---|---|
| `--jdk-internals` | Tìm class-level dependency tới JDK internal APIs |
| `--list-deps` | Liệt kê module dependency và package liên quan |
| `--list-reduced-deps` | Liệt kê module dependency sau khi rút gọn các cạnh được suy ra |
| `--print-module-deps` | In danh sách module dependency dạng phù hợp cho công cụ như `jlink` |
| `--missing-deps` | Tìm dependency không được phân giải |
| `--api-only` | Giới hạn phân tích dependency từ API public/protected của lớp public |

Nếu mục tiêu là tìm internal API, hãy dùng `--jdk-internals`. Chỉ xem danh sách module dependency hoặc package thông thường không thay thế được phép kiểm tra này.

Theo tài liệu JDK 16, `--jdk-internals` không kết hợp với các tùy chọn lọc `--package`, `--regex` và `--summary`. Nếu cần giới hạn phạm vi, hãy lựa chọn artifact hoặc class đầu vào phù hợp.

## 12. jdeps không phải công cụ quét mọi API deprecated

Một API có thể được đánh dấu deprecated nhưng vẫn là API công khai. Ngược lại, internal API có thể chưa được đánh dấu deprecated nhưng vẫn không phải hợp đồng được hỗ trợ cho ứng dụng.

`jdeps --jdk-internals` tìm dependency vào JDK internal APIs. Nó không thay thế việc kiểm tra các API deprecated.

Để khảo sát API deprecated trong ứng dụng, có thể dùng công cụ `jdeprscan` phù hợp với JDK. Hai công cụ trả lời hai câu hỏi khác nhau:

- `jdeps --jdk-internals`: mã đang phụ thuộc vào JDK internal APIs nào?
- `jdeprscan`: mã đang sử dụng API deprecated nào mà công cụ nhận diện được?

Khi nâng cấp JDK, nên xem cả hai báo cáo cùng với migration guide của phiên bản mục tiêu.

## 13. Thay thế internal API bằng API công khai

Khi báo cáo chỉ ra internal API, đừng vội thêm cờ JVM để mở quyền truy cập. Trước tiên, xác định tác vụ mà mã đang cần và tìm API Java SE tương ứng.

Ví dụ chuyển Base64:

```java
import java.util.Base64;

byte[] input = "Java 16".getBytes(java.nio.charset.StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);
```

Nếu không có API thay thế trực tiếp:

1. Đọc tài liệu của internal API để xác định hành vi mà ứng dụng đang dựa vào.
2. Kiểm tra API Java SE hoặc thư viện được duy trì có hỗ trợ use case tương đương.
3. Thay dependency và bổ sung test cho hành vi cần giữ.
4. Nâng cấp thư viện bên thứ ba nếu dependency nằm ngoài mã ứng dụng.
5. Chạy lại `jdeps --jdk-internals` sau khi build.

Không thay thế máy móc chỉ dựa trên tên lớp. API mới có thể có khác biệt về encoding, exception, thread safety, hiệu năng hoặc semantics.

## 14. Tích hợp kiểm tra vào quy trình build và CI

Nên chạy `jdeps` sau khi build artifact, khi đã có class file và dependency report. Một bước kiểm tra có thể thực hiện như sau:

```bash
jdeps --jdk-internals build/libs/service.jar
```

Lưu output thành artifact của CI để reviewer biết:

- Artifact nào đã được quét.
- JDK và phiên bản `jdeps` được dùng.
- Các internal API được phát hiện.
- Dependency nào sở hữu tham chiếu.
- Trạng thái xử lý: đã thay thế, đang chờ nâng cấp hoặc có ngoại lệ được chấp thuận.

Nếu dùng CI làm quality gate, hãy thiết lập chính sách dựa trên output và dependency đã được xác minh. Không giả định mọi phiên bản `jdeps` có cùng định dạng output hoặc tự động trả exit code khác 0 chỉ vì tìm thấy internal API; hãy xác nhận hành vi của tool và viết bước kiểm tra phù hợp với pipeline.

Khi dependency mới được thêm hoặc nâng cấp, chạy lại phép phân tích. Một thư viện mới có thể đưa internal API vào cây dependency dù mã ứng dụng không thay đổi.

## 15. Quy trình xử lý một cảnh báo jdeps

Khi nhận được cảnh báo, có thể đi theo các bước:

1. **Xác định lớp nguồn.** Tìm lớp ứng dụng hoặc thư viện được nêu trong output.
2. **Xác định internal API đích.** Ghi lại tên lớp/package và module sở hữu nếu biết.
3. **Tìm nguồn dependency.** Kiểm tra mã ứng dụng hay JAR bên thứ ba tạo tham chiếu.
4. **Đánh giá mức độ rủi ro.** API có bị đóng gói mạnh, bị loại bỏ hoặc thay đổi trong JDK mục tiêu không?
5. **Tìm API thay thế.** Ưu tiên Java SE API được tài liệu hóa.
6. **Nâng cấp thư viện.** Nếu dependency thuộc framework, kiểm tra phiên bản đã sửa.
7. **Chỉ dùng workaround hẹp khi cần.** `--add-exports` hoặc `--add-opens` có thể giải quyết một số tình huống cụ thể trong thời gian di trú, nhưng không làm internal API trở thành API ổn định.
8. **Kiểm thử runtime.** Chạy luồng sử dụng thư viện trên JDK production.
9. **Quét lại artifact.** Xác nhận dependency tĩnh đã được loại bỏ hoặc có ngoại lệ được ghi nhận.

Đừng đóng cảnh báo chỉ vì ứng dụng hiện vẫn chạy trên một JDK cụ thể. Internal API có thể còn tồn tại trong JDK hiện tại nhưng bị thay đổi hoặc loại bỏ trong bản sau.

## 16. Những giới hạn và sai lầm thường gặp

**Chỉ quét JAR ứng dụng.** Internal API có thể được gọi từ thư viện bên thứ ba. Hãy đưa dependency vào phạm vi phân tích.

**Không cung cấp class path hoặc module path.** Dependency thiếu có thể làm phạm vi phân tích không đầy đủ. Chuẩn bị đúng đường dẫn trước khi kết luận.

**Cho rằng không có output nghĩa là ứng dụng hoàn toàn an toàn.** Reflection, tên lớp động và cấu hình runtime có thể không được phát hiện.

**Cho rằng jdeps kiểm tra API deprecated.** Đây là nhiệm vụ khác; dùng công cụ phù hợp như `jdeprscan` khi cần.

**Dùng --illegal-access để sửa cảnh báo jdeps.** Tùy chọn này xử lý một cơ chế tương thích reflection cũ, không xóa tham chiếu bytecode tới internal API; trên Java 17 trở lên nó không khôi phục quyền truy cập cũ.

**Dùng --add-opens cho dependency tĩnh.** `--add-opens` phục vụ deep reflection. Tham chiếu trực tiếp tới kiểu nội bộ cần xử lý theo API công khai hoặc cơ chế export cụ thể trong giai đoạn chuyển tiếp.

**Tin tuyệt đối vào suggested replacement.** Gợi ý là điểm bắt đầu để điều tra. Cần kiểm tra semantics và test trước khi thay.

**Không phân tích multi-release JAR theo target runtime.** Chọn `--multi-release` phù hợp để quét đúng biến thể class được runtime sử dụng.

**Coi jdeps là kiểm thử runtime.** Công cụ không thực thi ứng dụng. Hãy kết hợp với integration test và kiểm tra framework reflection.

**Dựa vào định dạng output cố định trong CI.** Phiên bản JDK có thể thay đổi cách trình bày. Xác minh phiên bản tool và cách pipeline diễn giải output.

## 17. Ghi nhớ

- `jdeps --jdk-internals` tìm dependency tĩnh ở cấp lớp tới JDK internal APIs trong bytecode.
- Công cụ phân tích `.class`, thư mục class, JAR và các lớp được chỉ định trong class path.
- Dùng `--class-path` hoặc `--module-path` để đưa dependency cần kiểm tra vào phạm vi.
- Dùng `--multi-release` để chọn biến thể class của multi-release JAR.
- Output có thể nêu lớp nguồn, internal API và suggested replacement nếu có.
- Không có cảnh báo không chứng minh ứng dụng không dùng reflection hoặc nạp lớp động.
- `jdeps --jdk-internals` khác với `jdeprscan` và các chế độ liệt kê module dependency.
- Thay internal API bằng API công khai được tài liệu hóa; nâng cấp dependency bên thứ ba khi cần.
- Không dùng `--illegal-access` như cách khắc phục trên JDK hiện đại.
- Tích hợp quét vào CI sau khi build và lưu báo cáo để theo dõi qua các lần nâng cấp.
- Kết hợp phân tích tĩnh với integration test trên JDK production.

`jdeps --jdk-internals` giúp tìm các dependency trực tiếp vào implementation nội bộ của JDK trước khi chúng trở thành lỗi nâng cấp. Dùng đúng phạm vi artifact, class path và module path, sau đó thay dependency bằng API công khai và kiểm thử runtime sẽ giúp ứng dụng Java duy trì tính tương thích trên các JDK hiện đại.

## Tài liệu tham khảo

- [The jdeps Command – Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jdeps.html) — cú pháp, đầu vào và tùy chọn `--jdk-internals`.
- [The java Command – Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/java.html) — ngữ cảnh `--illegal-access` trong giai đoạn di trú.
- [JEP 396 – Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396) — thay đổi mặc định strong encapsulation trong Java 16.
- [JEP 403 – Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403) — hoàn tất đóng gói mạnh trong Java 17.
- [Preparing for Migration – Oracle JDK Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html) — ví dụ `jdeps --jdk-internals` và giới hạn của phân tích tĩnh.

