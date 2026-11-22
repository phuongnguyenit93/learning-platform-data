# Quét API deprecated và forRemoval bằng jdeprscan

## 1. Vai trò của jdeprscan trong chuyển đổi Java

Khi nâng JDK, một rủi ro thường gặp là mã nguồn hoặc thư viện vẫn gọi các API của Java đã bị đánh dấu deprecated. Một API deprecated vẫn có thể hoạt động ở phiên bản hiện tại, nhưng nhà phát triển nền tảng đã công bố rằng API đó không còn được khuyến nghị sử dụng. Ở một số trường hợp, API còn được đánh dấu để loại bỏ trong một phiên bản Java tương lai.

jdeprscan là công cụ dòng lệnh đi kèm JDK, dùng để quét bytecode Java và tìm các tham chiếu đến API JDK đã deprecated trong phiên bản nền tảng được chọn. Công cụ giúp nhóm phát hiện những điểm cần xem xét trước khi nâng runtime, thay thư viện hoặc chuyển sang một phiên bản Java mục tiêu mới.

Trong quá trình migration, jdeprscan đặc biệt hữu ích để:

- Tìm các lớp và phương thức trong artifact của ứng dụng đang tham chiếu đến API JDK deprecated.
- Tách riêng những API được đánh dấu for removal để ưu tiên xử lý.
- Xác định vị trí tham chiếu trong bytecode, từ đó quay lại mã nguồn hoặc dependency liên quan.
- So sánh kết quả quét giữa các phiên bản JDK và theo dõi việc giảm dần các tham chiếu rủi ro.
- Tạo bằng chứng kỹ thuật cho kế hoạch thay thế API trước khi API bị loại bỏ.

jdeprscan là một bước phân tích tĩnh trên class file. Nó không thay thế compiler, unit test, integration test, kiểm thử runtime hoặc việc đọc migration guide của JDK/framework. Kết quả cần được kết hợp với các nguồn bằng chứng đó để quyết định cách sửa.

## 2. Deprecated và forRemoval có ý nghĩa gì?

Java cung cấp annotation java.lang.Deprecated để đánh dấu API không còn được khuyến nghị sử dụng. Annotation có thể áp dụng cho kiểu, phương thức, constructor, field hoặc thành phần được hỗ trợ theo quy tắc của ngôn ngữ.

Từ Java 9, annotation có thêm hai thuộc tính quan trọng:

- since: phiên bản mà API được đánh dấu deprecated.
- forRemoval: cho biết API đã deprecated và được dự định loại bỏ trong một phiên bản Java tương lai.

Ví dụ:

~~~java
@Deprecated(since = "9")
public void legacyOperation() {
    // API cũ vẫn tồn tại nhưng không còn được khuyến nghị.
}

@Deprecated(since = "17", forRemoval = true)
public void operationScheduledForRemoval() {
    // API cần được ưu tiên thay thế trước khi bị loại bỏ.
}
~~~

Hai trạng thái này không nên được xem là tương đương:

| Trạng thái | Ý nghĩa | Cách xử lý trong migration |
|---|---|---|
| Deprecated | API không còn được khuyến nghị; chưa có tuyên bố rằng nó sẽ bị loại bỏ. | Xác định API thay thế, đánh giá chi phí và lập kế hoạch chuyển đổi phù hợp. |
| Deprecated for removal | API được đánh dấu rõ ràng là dự kiến bị loại bỏ trong tương lai. | Ưu tiên cao; tìm cách thay thế và kiểm tra phiên bản JDK mục tiêu trước khi nâng cấp. |
| Đã bị loại bỏ | API không còn tồn tại trong nền tảng mục tiêu. | Tham chiếu có thể gây lỗi biên dịch, liên kết hoặc runtime; phải chuyển sang API còn được hỗ trợ. |

forRemoval là tín hiệu về ý định loại bỏ, không phải cam kết rằng API sẽ biến mất ngay ở bản Java kế tiếp. Nhóm cần tra cứu tài liệu của phiên bản JDK cụ thể để biết thời điểm, API thay thế và hướng dẫn migration.

Một API có thể đã deprecated trong nhiều phiên bản nhưng vẫn chưa bị loại bỏ. Ngược lại, khi API đã bị loại khỏi JDK mục tiêu, việc quét bằng một phiên bản nền tảng đã không còn API đó có thể cho kết quả khác với việc quét ở phiên bản mà API vẫn còn tồn tại. Vì vậy, cần chọn release phù hợp với câu hỏi đang kiểm tra và không diễn giải mọi thông báo không phân giải được thành kết luận “deprecated”.

## 3. jdeprscan quét gì và không quét gì?

jdeprscan đọc class file trong một thư mục, một JAR hoặc một class được chỉ định, rồi đối chiếu các tham chiếu bytecode với danh sách API JDK deprecated của release được chọn. Công cụ có thể báo cáo tham chiếu đến API deprecated trong mã đã biên dịch mà không cần biên dịch lại source code.

### 3.1. Phạm vi phát hiện

Thông thường, công cụ có thể tìm được các tham chiếu trực tiếp trong bytecode như:

- Lệnh gọi phương thức deprecated.
- Tham chiếu đến constructor hoặc field deprecated.
- Tham chiếu kiểu hoặc thành phần nền tảng đã được đánh dấu deprecated.
- Tham chiếu xuất hiện trong class file thuộc artifact được quét, nếu công cụ có thể phân tích và phân giải chúng.

Kết quả thường chỉ ra class chứa tham chiếu và API deprecated được sử dụng. Tùy trường hợp, có thể cần đọc mã nguồn tương ứng hoặc dependency tree để xác định thành phần sở hữu lời gọi.

### 3.2. Những gì công cụ không chứng minh được

jdeprscan không phải bộ phân tích mọi hành vi của ứng dụng. Nó có những giới hạn cần hiểu rõ:

- Công cụ tập trung vào API của JDK. Nó không phải công cụ tổng quát để tìm mọi API deprecated do thư viện bên thứ ba tự khai báo.
- Công cụ quét class file, không phân tích đầy đủ mã nguồn chưa biên dịch.
- Nó không bảo đảm phát hiện mọi lời gọi được tạo động qua reflection, tên lớp/phương thức được lưu dưới dạng chuỗi, cấu hình runtime hoặc mã được sinh ra sau thời điểm quét.
- Nó không chứng minh đường đi thực thi của một tham chiếu. Một class có thể chứa lời gọi deprecated nhưng nhánh code đó chưa từng được chạy trong production.
- Nó không thay thế kiểm thử tương thích binary, kiểm thử chức năng, kiểm thử bảo mật hoặc đo hiệu năng.
- Nếu thiếu dependency cần thiết để phân giải kiểu, kết quả có thể chứa thông tin không đầy đủ hoặc cảnh báo liên quan đến phân giải. Cần cung cấp classpath thích hợp và phân biệt lỗi phân giải với phát hiện deprecated thực sự.

Điểm quan trọng là phạm vi đầu vào. Khi quét JAR ứng dụng, công cụ kiểm tra các class file trong JAR đó. Dependency nằm trong classpath được dùng để hỗ trợ phân giải tham chiếu; việc thêm dependency vào classpath không có nghĩa là mọi class trong dependency đó cũng tự động được quét. Muốn kiểm tra một thư viện bên thứ ba, cần quét artifact của thư viện đó như một đầu vào riêng.

### 3.3. Phân biệt với các công cụ khác

Các công cụ phân tích JDK có phạm vi khác nhau:

| Công cụ | Mục đích chính | Câu hỏi được trả lời |
|---|---|---|
| jdeprscan | Quét class file để tìm tham chiếu đến API JDK deprecated. | Artifact có sử dụng API JDK đã deprecated hoặc forRemoval không? |
| javac với cảnh báo deprecation | Phát cảnh báo trong quá trình biên dịch source code. | Mã nguồn đang biên dịch có gọi API deprecated không? |
| jdeps --jdk-internals | Phân tích dependency đến API nội bộ của JDK. | Artifact có phụ thuộc vào JDK internal API không? |
| Unit/integration test | Thực thi các luồng ứng dụng đã chọn. | Hành vi của ứng dụng có còn đúng trên môi trường mục tiêu không? |

Một artifact có thể không có kết quả deprecated nhưng vẫn phụ thuộc vào JDK internal API. Ngược lại, một tham chiếu deprecated không nhất thiết là tham chiếu đến API nội bộ. Vì vậy, jdeprscan và jdeps giải quyết hai loại rủi ro khác nhau.

## 4. Chuẩn bị môi trường quét

jdeprscan được cung cấp cùng JDK. Hãy dùng bản JDK có công cụ này và kiểm tra phiên bản trước khi quét:

~~~bash
jdeprscan --version
~~~

Trên Windows PowerShell:

~~~powershell
Get-Command jdeprscan -All | Select-Object Source
jdeprscan --version
~~~

Nếu lệnh không được tìm thấy, kiểm tra thư mục bin của JDK và PATH. Có thể gọi trực tiếp executable trong JAVA_HOME:

~~~powershell
& "$env:JAVA_HOME\bin\jdeprscan.exe" --version
~~~

Trên Linux/macOS:

~~~bash
"$JAVA_HOME/bin/jdeprscan" --version
~~~

Nên ghi lại phiên bản đầy đủ và nhà cung cấp JDK cung cấp công cụ. Phiên bản jdeprscan quyết định các release mà công cụ có thể dùng để đối chiếu. Nếu cần quét theo một release mới hơn mà công cụ hiện tại không hỗ trợ, hãy dùng jdeprscan từ JDK mới hơn có hỗ trợ release đó.

Trước khi chạy, chuẩn bị:

1. Artifact đã build thành công, ví dụ JAR ứng dụng hoặc thư mục class file.
2. Release JDK cần đối chiếu.
3. Classpath chứa dependency cần thiết để phân giải tham chiếu.
4. Danh sách các artifact cần quét, gồm ứng dụng và các dependency quan trọng nếu phạm vi yêu cầu.
5. Nơi lưu log và thông tin phiên bản công cụ, thời điểm quét, commit hoặc artifact version.

Không nên chỉ quét thư mục source hoặc một JAR cũ còn sót lại trong workspace. Hãy chắc chắn artifact đầu vào thuộc đúng commit và build configuration đang được đánh giá.

## 5. Các tùy chọn chính của jdeprscan

Các tùy chọn thường dùng gồm:

| Tùy chọn | Công dụng |
|---|---|
| --release RELEASE | Chọn release Java dùng làm mốc đối chiếu API deprecated. |
| --for-removal | Chỉ tập trung vào các API deprecated được đánh dấu forRemoval. |
| --class-path PATH | Cung cấp classpath để công cụ phân giải các kiểu và tham chiếu liên quan. |
| --list | Liệt kê các API deprecated của release được chọn thay vì quét một artifact cụ thể. |
| --verbose | Hiển thị thông tin chi tiết hơn trong quá trình quét. |
| --version | Hiển thị phiên bản công cụ. |
| --full-version | Hiển thị thông tin phiên bản đầy đủ. |
| --help | Hiển thị hướng dẫn sử dụng của bản công cụ đang chạy. |

Tập release được hỗ trợ và chi tiết tùy chọn phụ thuộc vào phiên bản JDK cài đặt. Khi cần cú pháp chính xác, luôn kiểm tra jdeprscan --help của chính JDK được dùng trong pipeline.

### 5.1. Chọn release

--release xác định phiên bản Java mà danh sách API deprecated được dùng làm mốc. Ví dụ:

~~~bash
jdeprscan --release 17 app.jar
~~~

Lệnh trên quét artifact theo danh sách API deprecated của Java 17. Khi migration sang một phiên bản mới hơn, hãy chọn release phù hợp với mục tiêu cần đánh giá và khả năng hỗ trợ của jdeprscan đang cài.

Có thể quét cùng một artifact theo nhiều release được công cụ hỗ trợ để quan sát cách trạng thái deprecated thay đổi theo thời gian. Tuy nhiên, kết quả của mỗi release phải được lưu riêng, vì tập API và trạng thái deprecated có thể khác nhau.

### 5.2. Chỉ quét API forRemoval

Để tập trung vào API có mức ưu tiên cao:

~~~bash
jdeprscan --release 17 --for-removal app.jar
~~~

Tùy chọn --for-removal giới hạn kết quả vào các API được đánh dấu deprecated for removal trong release được chọn. Đây là cách hữu ích để tạo danh sách xử lý ưu tiên trong migration.

Kết quả không có phát hiện forRemoval không đồng nghĩa với việc artifact không sử dụng bất kỳ API deprecated nào. Hãy chạy thêm lượt quét thông thường nếu mục tiêu là kiểm kê toàn bộ deprecated API.

### 5.3. Liệt kê API deprecated của một release

Có thể xem danh sách API mà jdeprscan nhận diện ở release cụ thể:

~~~bash
jdeprscan --list --release 17
~~~

Để chỉ liệt kê nhóm được đánh dấu forRemoval:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

Danh sách này giúp tra cứu tên API và chuẩn bị đối chiếu, nhưng không phải kết quả quét ứng dụng. Nó không cho biết artifact nào đang sử dụng các API đó.

## 6. Quét JAR và thư mục class file

### 6.1. Quét JAR ứng dụng

Sau khi build, chạy jdeprscan trên JAR cần đánh giá:

~~~bash
jdeprscan --release 21 build/libs/application.jar
~~~

Đổi release và đường dẫn artifact theo dự án thực tế. Nếu ứng dụng tạo nhiều JAR, hãy xác định rõ JAR nào là artifact triển khai và JAR nào là thư viện dùng chung.

Để chỉ tìm API forRemoval:

~~~bash
jdeprscan --release 21 --for-removal build/libs/application.jar
~~~

Nên thực hiện cả hai lượt khi cần baseline đầy đủ:

1. Quét tất cả deprecated API để có bức tranh tổng thể.
2. Quét riêng forRemoval để lập danh sách ưu tiên xử lý.

### 6.2. Quét thư mục class file

Nếu build tạo class file trong một thư mục:

~~~bash
jdeprscan --release 21 build/classes/java/main
~~~

Với cấu trúc module khác, thay đường dẫn bằng thư mục chứa class file đã biên dịch. Chỉ định đúng thư mục output của source set hoặc module cần quét; một thư mục gốc không chứa class file sẽ không cung cấp bằng chứng hữu ích.

### 6.3. Cung cấp classpath

Một class file có thể tham chiếu đến kiểu được khai báo trong dependency khác. Cung cấp classpath giúp jdeprscan phân giải các tham chiếu đó:

~~~bash
jdeprscan --release 21 --class-path "lib/*" build/libs/application.jar
~~~

Nếu cần chỉ định nhiều đường dẫn, dùng dấu phân cách classpath của hệ điều hành:

- Windows: dấu chấm phẩy (;).
- Linux và macOS: dấu hai chấm (:).

Ví dụ trên Linux/macOS:

~~~bash
jdeprscan --release 21 --class-path "lib/a.jar:lib/b.jar" build/libs/application.jar
~~~

Ví dụ trên Windows:

~~~powershell
jdeprscan --release 21 --class-path "lib\a.jar;lib\b.jar" build\libs\application.jar
~~~

Classpath giúp công cụ phân giải tham chiếu. Nó không tự biến mọi JAR trong classpath thành mục tiêu quét. Nếu muốn kiểm tra deprecated API được sử dụng bên trong thư viện bên thứ ba, cần chạy jdeprscan trực tiếp trên từng JAR thư viện đó.

### 6.4. Quét dependency của ứng dụng

Để có bức tranh rộng hơn, lập danh sách dependency runtime hoặc dependency đóng gói của ứng dụng, sau đó quét các artifact quan trọng riêng biệt. Với mỗi dependency, ghi lại:

- Tên artifact và phiên bản.
- Nguồn lấy dependency và checksum nếu có.
- Phạm vi sử dụng: compile, runtime, test hoặc build-time.
- Release được dùng để quét.
- Kết quả deprecated và forRemoval.

Ưu tiên các thư viện nền tảng có nhiều tương tác với JDK như framework, ORM, database driver, HTTP client, logging, serialization, security, bytecode manipulation và thư viện tích hợp. Việc một dependency chưa được quét phải được ghi rõ; không suy ra rằng dependency đó sạch chỉ vì classpath của ứng dụng đã được cung cấp.

## 7. Quy trình xử lý kết quả quét

Kết quả jdeprscan là đầu vào cho việc điều tra. Không nên thay API ngay chỉ dựa trên tên được in ra; trước hết cần xác định tham chiếu đến từ mã nguồn nào, dependency nào và release nào.

### 7.1. Xác định class sở hữu tham chiếu

Khi công cụ báo một class sử dụng API deprecated:

1. Xác định class đó thuộc artifact ứng dụng hay dependency bên ngoài.
2. Nếu thuộc ứng dụng, tìm source tương ứng trong module và kiểm tra lời gọi.
3. Nếu thuộc dependency, xác định dependency trực tiếp hoặc bắc cầu sở hữu class.
4. Đối chiếu với release mà API bị đánh dấu deprecated hoặc forRemoval.
5. Kiểm tra tài liệu JDK để tìm API thay thế và điều kiện migration.

Tên class trong báo cáo thường là điểm bắt đầu để tra cứu. Nếu class được tạo tự động, cần tìm generator, annotation processor hoặc thư viện tạo mã thay vì sửa trực tiếp output có thể bị ghi đè ở lần build sau.

### 7.2. Phân loại phát hiện

Có thể phân loại phát hiện theo nguồn và mức độ:

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Mã nguồn do dự án sở hữu, deprecated | Một phương thức trong module gọi API JDK cũ. | Tìm API thay thế, cập nhật mã và thêm kiểm thử. |
| Mã nguồn do dự án sở hữu, forRemoval | Lời gọi đến API được dự kiến loại bỏ. | Ưu tiên sửa trước khi nâng JDK; xác nhận thay thế trên release mục tiêu. |
| Dependency trực tiếp | Thư viện do dự án khai báo chứa class gọi API deprecated. | Kiểm tra bản nâng cấp của thư viện hoặc thay thế dependency. |
| Dependency bắc cầu | Một thư viện khác kéo vào thành phần có tham chiếu deprecated. | Dùng dependency insight/tree để tìm nguồn và điều chỉnh bộ phiên bản phù hợp. |
| Code generated | Class được sinh từ schema, processor hoặc generator. | Nâng/cấu hình generator rồi sinh lại mã; không chỉ sửa output tạm. |
| Chưa xác định được nguồn | Báo cáo có class nhưng thiếu thông tin artifact hoặc classpath. | Bổ sung bằng chứng build, classpath và danh sách artifact rồi quét lại. |

### 7.3. Chọn API thay thế

Không phải mọi API deprecated đều có thể thay bằng một phương thức cùng tên hoặc một lớp mới tương đương hoàn toàn. Khi thay thế, cần xem xét:

- Chữ ký và kiểu dữ liệu đầu vào/đầu ra.
- Giá trị mặc định, exception và quy tắc xử lý lỗi.
- Hành vi về timezone, locale, encoding và định dạng dữ liệu.
- Thread-safety, lifecycle, resource management và hiệu năng.
- Khả năng tương thích với các phiên bản JDK mà dự án còn hỗ trợ.
- Ảnh hưởng đến dữ liệu lưu trữ, giao thức và API public.

Ví dụ, thay một API ngày giờ cũ bằng java.time có thể làm thay đổi kiểu dữ liệu và cách biểu diễn timezone. Khi đó, ngoài sửa compile, cần kiểm tra serialization, database mapping và hợp đồng HTTP nếu các lớp này sử dụng kiểu dữ liệu liên quan.

Nếu API deprecated không có thay thế trực tiếp, cần đọc tài liệu migration của JDK, đánh giá cách thiết kế lại phần sử dụng và ghi lại quyết định kỹ thuật. Không nên chỉ tắt cảnh báo hoặc giữ tham chiếu forRemoval mà không có lý do và kế hoạch rõ ràng.

## 8. Tổ chức quét theo nhiều giai đoạn JDK

Trong migration, một lượt quét duy nhất thường không trả lời được tất cả câu hỏi. Nên xác định rõ mục đích của từng lượt:

| Giai đoạn | Release đối chiếu | Mục tiêu |
|---|---|---|
| Baseline hiện tại | Release đang được dùng hoặc release mà artifact được hỗ trợ | Ghi nhận các deprecated API đang tồn tại trong artifact. |
| Rà soát ưu tiên | Cùng release baseline với --for-removal | Lập danh sách API có nguy cơ bị loại bỏ cần xử lý trước. |
| Đánh giá mục tiêu | Release JDK mục tiêu được công cụ hỗ trợ | Xác định các API deprecated theo nền tảng mục tiêu và phát hiện cần điều tra. |
| Sau khi sửa | Cùng release và tùy chọn như baseline | So sánh kết quả trước/sau bằng cùng điều kiện quét. |

Nếu API đã bị loại khỏi release mục tiêu, việc quét theo release đó không phải lúc nào cũng cho một báo cáo deprecated rõ ràng. Có thể xuất hiện vấn đề phân giải vì API không còn trong nền tảng. Hãy đối chiếu với release mà API vẫn tồn tại và được đánh dấu deprecated/forRemoval, đồng thời build và test trực tiếp trên JDK mục tiêu để xác nhận việc loại bỏ.

Khi công cụ không hỗ trợ release mục tiêu, dùng jdeprscan từ một JDK mới hơn có hỗ trợ release đó. Không dùng một công cụ cũ rồi suy luận rằng không có phát hiện nghĩa là artifact tương thích với JDK tương lai.

## 9. Tích hợp jdeprscan vào CI

Đưa bước quét vào CI giúp kết quả được tạo lại trên cùng artifact và lưu cùng bằng chứng build. Một job cơ bản có thể gồm:

1. Chọn JDK cung cấp jdeprscan và hỗ trợ release cần kiểm tra.
2. Build artifact từ commit đang chạy.
3. Xác định đúng JAR hoặc thư mục class file.
4. Quét tất cả deprecated API.
5. Quét riêng API forRemoval.
6. Lưu log, phiên bản công cụ, release, commit và artifact identifier.
7. Đánh giá kết quả theo chính sách của dự án.

Ví dụ với shell trong pipeline:

~~~bash
jdeprscan --version
jdeprscan --release 21 build/libs/application.jar
jdeprscan --release 21 --for-removal build/libs/application.jar
~~~

Nếu cần lưu báo cáo:

~~~bash
jdeprscan --release 21 build/libs/application.jar \
  > build/reports/jdeprscan-all.txt 2>&1

jdeprscan --release 21 --for-removal build/libs/application.jar \
  > build/reports/jdeprscan-for-removal.txt 2>&1
~~~

Với PowerShell:

~~~powershell
jdeprscan --version
jdeprscan --release 21 build\libs\application.jar *> build\reports\jdeprscan-all.txt
jdeprscan --release 21 --for-removal build\libs\application.jar *> build\reports\jdeprscan-for-removal.txt
~~~

Đường dẫn báo cáo phải tồn tại trước khi ghi. Cần kiểm tra exit code và nội dung log của công cụ theo phiên bản đang dùng; không nên mặc định rằng mọi phát hiện deprecated đều khiến jdeprscan trả về exit code khác 0. Nếu tổ chức muốn chặn pipeline khi có API forRemoval, hãy xây dựng bước policy riêng dựa trên kết quả đã được kiểm chứng và phân biệt phát hiện với lỗi công cụ hoặc lỗi phân giải.

### 9.1. Chính sách CI theo mức độ

Một chính sách thực tế có thể chia thành các mức:

- **forRemoval mới xuất hiện:** yêu cầu điều tra và xử lý trước khi chấp nhận migration, hoặc cần phê duyệt ngoại lệ có thời hạn.
- **Deprecated thông thường mới xuất hiện:** tạo cảnh báo hoặc yêu cầu giải thích tùy mức độ ảnh hưởng.
- **Phát hiện đã tồn tại:** duy trì baseline để không làm tăng thêm số lượng; xử lý dần theo kế hoạch.
- **Lỗi quét hoặc thiếu artifact:** coi là thiếu bằng chứng, không diễn giải thành “không có deprecated API”.

Nếu áp dụng baseline, hãy lưu kết quả theo commit hoặc artifact fingerprint, release quét, phiên bản jdeprscan và loại quét. Chỉ so sánh hai kết quả có điều kiện tương đương. Khi đổi JDK công cụ, release đối chiếu hoặc classpath, cần ghi nhận thay đổi để tránh so sánh sai.

### 9.2. Quét nhiều module

Với repository nhiều module, mỗi module có thể tạo artifact và dependency graph riêng. Cần xác định module nào có mã Java, module nào đóng gói JAR, và module nào chỉ là tập hợp hoặc module nền tảng. Quét từng artifact có ý nghĩa thay vì chỉ quét một JAR đại diện.

Nên giữ kết quả theo module để có thể truy nguồn phát hiện về nhóm sở hữu. Nếu nhiều module cùng kéo một dependency, có thể quét dependency đó một lần ở cấp artifact nhưng vẫn ghi nhận các module sử dụng nó. Không gộp toàn bộ log mà mất thông tin nguồn.

## 10. Đọc kết quả và tránh kết luận sai

Khi nhận được output, hãy phân biệt bốn tình huống:

1. **Phát hiện deprecated:** công cụ tìm thấy tham chiếu đến API JDK đã deprecated trong phạm vi quét.
2. **Phát hiện forRemoval:** tham chiếu đến API được đánh dấu dự kiến loại bỏ; cần ưu tiên điều tra.
3. **Không phân giải được tham chiếu:** công cụ thiếu classpath hoặc API không tồn tại trong release đối chiếu; cần tìm nguyên nhân trước khi kết luận.
4. **Không có phát hiện:** không tìm thấy tham chiếu phù hợp trong các class file đã quét theo release và phạm vi đầu vào đó.

“Không có phát hiện” chỉ có ý nghĩa trong phạm vi đã quét. Nếu chưa quét dependency, code generated, plugin hoặc class được nạp động, kết quả không chứng minh toàn hệ thống không sử dụng deprecated API.

Khi một lượt quét báo lỗi, không nên xóa báo cáo hoặc xem nó như kết quả sạch. Hãy ghi nhận lệnh, phiên bản jdeprscan, release, artifact, classpath và thông báo lỗi. Sau đó sửa điều kiện quét hoặc xác định rõ phần không thể phân tích.

## 11. Ví dụ quy trình xử lý một phát hiện forRemoval

Giả sử jdeprscan báo một class trong ứng dụng tham chiếu đến API JDK được đánh dấu forRemoval:

1. Xác định class thuộc module và source file nào.
2. Tìm lời gọi hoặc tham chiếu tương ứng trong source; nếu không thấy, kiểm tra code generated hoặc bytecode được đóng gói từ dependency.
3. Đọc tài liệu JDK để xác định release deprecated, trạng thái forRemoval và API thay thế.
4. Kiểm tra API thay thế trên JDK mục tiêu và các JDK mà dự án còn hỗ trợ.
5. Sửa source hoặc nâng dependency/generator sở hữu lời gọi.
6. Chạy compile, unit test và integration test liên quan đến hành vi bị thay đổi.
7. Build lại artifact từ cùng cấu hình.
8. Chạy lại jdeprscan với cùng release, classpath và tùy chọn như baseline.
9. Lưu báo cáo mới và giải thích mọi phát hiện còn lại.

Nếu phát hiện nằm trong thư viện bên thứ ba, cần kiểm tra phiên bản mới của thư viện có loại bỏ tham chiếu đó hay không. Nếu chưa có bản sửa, đánh giá lựa chọn thay thư viện, thay adapter hoặc duy trì ngoại lệ có thời hạn. Không sửa bytecode trong JAR bên thứ ba như một cách xử lý thông thường vì thay đổi đó khó tái lập và có thể làm sai chữ ký hoặc hành vi thư viện.

## 12. Mẫu ghi nhận kết quả quét

Một báo cáo nên giữ đủ dữ liệu để người khác chạy lại và hiểu giới hạn của kết quả:

| Trường | Nội dung |
|---|---|
| Module / artifact | Tên module, đường dẫn JAR hoặc thư mục class file. |
| Artifact identity | Version, commit SHA hoặc fingerprint của artifact. |
| jdeprscan version | Phiên bản công cụ và JDK cung cấp công cụ. |
| Release đối chiếu | Giá trị --release được sử dụng. |
| Scan mode | Toàn bộ deprecated hoặc chỉ --for-removal. |
| Classpath | Các dependency được cung cấp để phân giải tham chiếu. |
| Findings | Danh sách class/API được phát hiện và nguồn sở hữu nếu xác định được. |
| Resolution issues | Cảnh báo hoặc lỗi phân giải, thiếu classpath hay artifact không đọc được. |
| Decision | Sửa, nâng dependency, thay thế, chấp nhận ngoại lệ hay cần điều tra thêm. |
| Evidence | Log, lệnh đã chạy, thời điểm và môi trường thực hiện. |

Ví dụ bảng theo dõi:

| Artifact | API deprecated | forRemoval | Nguồn | Quyết định | Trạng thái |
|---|---|---|---|---|---|
| application.jar | API được nêu trong báo cáo | Có/Không | Module hoặc dependency | Thay API / nâng thư viện / điều tra | Mở / Đã xử lý / Ngoại lệ |

Không điền tên API hoặc kết quả giả định vào báo cáo. Nếu chưa xác định được nguồn, ghi “chưa xác định” và tiếp tục truy vết bằng classpath, dependency tree hoặc nội dung artifact.

## 13. Checklist vận hành cho một lượt quét

Trước khi chạy:

- Xác định JDK cung cấp jdeprscan và kiểm tra phiên bản công cụ.
- Xác định release cần đối chiếu và xác nhận công cụ hỗ trợ release đó.
- Build đúng commit và xác định artifact đầu vào.
- Chuẩn bị classpath cần thiết để phân giải.
- Xác định có cần quét dependency riêng hay không.

Trong khi chạy:

- Chạy lượt quét toàn bộ deprecated API.
- Chạy lượt riêng với --for-removal.
- Lưu nguyên lệnh và output, bao gồm cảnh báo hoặc lỗi.
- Không đưa bí mật vào log hoặc báo cáo.

Sau khi chạy:

- Phân biệt phát hiện deprecated, forRemoval và lỗi phân giải.
- Xác định class và artifact sở hữu từng tham chiếu.
- Tra cứu API thay thế và đánh giá hành vi.
- Tạo hạng mục migration, kiểm thử và quét lại.
- Lưu baseline và ngoại lệ có người phụ trách, lý do, thời hạn.

## 14. Kết luận về việc sử dụng jdeprscan

jdeprscan giúp nhóm chuyển đổi Java phát hiện các tham chiếu đến API JDK deprecated trong bytecode. Tùy chọn --for-removal giúp làm nổi bật những API cần được ưu tiên thay thế vì đã có dấu hiệu sẽ bị loại bỏ. Khi kết hợp với --release, classpath phù hợp và việc quét từng artifact, nhóm có thể xây dựng một baseline rõ ràng cho ứng dụng và các dependency quan trọng.

Giá trị của công cụ phụ thuộc vào phạm vi đầu vào và cách diễn giải kết quả. Cần phân biệt mã nguồn dự án với dependency, API deprecated với API nội bộ, phát hiện thực sự với lỗi phân giải, và bytecode target với runtime. Quét lại sau mỗi thay đổi bằng cùng điều kiện giúp chứng minh tiến độ xử lý; build và kiểm thử trên JDK mục tiêu mới xác nhận được ứng dụng có thể tiếp tục hoạt động trong môi trường dự kiến.
