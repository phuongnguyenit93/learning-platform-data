# Công bố mức Java tối thiểu và thời điểm ngừng hỗ trợ phiên bản cũ

## 1. Bối cảnh của việc công bố chính sách Java

Trong quá trình **Java Advance Compatibility Migration**, thư viện hoặc ứng dụng có thể cần nâng JDK để sử dụng API mới, đáp ứng yêu cầu bảo mật, nâng framework, đổi build tool hoặc đơn giản hóa việc vận hành. Tuy nhiên, phía sử dụng sản phẩm không phải lúc nào cũng có thể chuyển JDK cùng thời điểm.

Một thư viện Java đã công bố API có thể được dùng bởi nhiều nhóm: ứng dụng khách đã biên dịch từ lâu, plugin được phân phối độc lập, dịch vụ chạy trong container riêng, batch job hoặc hệ thống của đối tác. Khi sản phẩm nâng mức Java tối thiểu mà không thông báo, người dùng có thể chỉ phát hiện vấn đề sau khi triển khai, qua lỗi khởi động, lỗi liên kết class hoặc dependency không tương thích.

Vì vậy, việc công bố **mức Java tối thiểu** và **thời điểm ngừng hỗ trợ Java cũ** là một phần của tiến hóa API, không chỉ là thông báo thay đổi môi trường build. Công bố phải giúp consumer biết:

- Từ phiên bản sản phẩm nào cần Java tối thiểu bao nhiêu?
- Java phiên bản nào được kiểm thử, được hỗ trợ chính thức và còn nhận bản vá?
- Phiên bản sản phẩm nào vẫn hoạt động trên Java cũ trong giai đoạn chuyển tiếp?
- Ngày nào kết thúc hỗ trợ thông thường, ngày nào kết thúc hoàn toàn việc phát hành bản vá cho dòng cũ?
- Người dùng cần làm gì, theo mốc nào, và có thể tìm tài liệu migration ở đâu?
- Đâu là hành vi dự kiến nếu tiếp tục chạy trên JDK không được hỗ trợ?

Một tuyên bố ngắn như “từ nay hỗ trợ Java 21” là chưa đủ, vì nó không nói rõ Java 17 còn được hỗ trợ hay không, runtime cần Java 21 hay chỉ build cần Java 21, và các bản vá cho nhánh sản phẩm cũ sẽ được duy trì đến ngày nào.

## 2. Các khái niệm phải phân biệt

### 2.1. Minimum required Java version

**Mức Java tối thiểu bắt buộc** là phiên bản Java thấp nhất mà một bản phát hành của sản phẩm yêu cầu trong phạm vi đã công bố.

Với thư viện Java, đây thường là mức runtime tối thiểu của ứng dụng sử dụng thư viện và có thể gắn với API nền tảng mà thư viện sử dụng. Với ứng dụng triển khai, đây có thể là runtime cần để khởi động artifact hoặc base image Java tối thiểu mà deployment phải cung cấp.

Ví dụ minh họa:

> Library 3.x yêu cầu Java 21 trở lên để chạy. Library 2.x vẫn cung cấp bản phát hành tương thích với Java 17 trong thời gian hỗ trợ được công bố.

Từ “trở lên” mô tả yêu cầu phiên bản tối thiểu; nó không tự tạo cam kết rằng **mọi** phiên bản Java tương lai đều được chứng nhận. Cần công bố riêng những phiên bản đã được kiểm thử và phạm vi hỗ trợ chính thức.

### 2.2. Minimum supported vs. tested vs. recommended

| Thuật ngữ | Nội dung | Cách diễn đạt trong tài liệu |
|---|---|---|
| Minimum required Java | Phiên bản thấp nhất mà bản phát hành yêu cầu để chạy hoặc sử dụng. | “Minimum runtime: Java 21.” |
| Supported Java versions | Những phiên bản Java thuộc chính sách hỗ trợ và nhận xử lý lỗi theo điều kiện công bố. | “Supported and tested: Java 21.” |
| Recommended Java | Phiên bản Java được khuyến nghị cho triển khai mới. | “Recommended deployment runtime: Java 21 with current security updates.” |
| Build JDK | JDK chạy Maven, Gradle, plugin và các bước build. | “Build tool runs on JDK 21.” |
| Compiler toolchain | JDK được sử dụng để biên dịch mã nguồn. | “Compile toolchain: JDK 21.” |
| Bytecode/API target | Mức bytecode và Java API mà artifact được phép tham chiếu. | “Compile with --release 17 for the Java 17 compatible branch.” |
| End of regular support | Mốc dừng sửa lỗi thông thường hoặc hỗ trợ kỹ thuật theo chính sách. | “Java 17 maintenance support ends on the specified date.” |
| End of life / end of support | Mốc dừng các hình thức hỗ trợ còn lại theo tuyên bố chính thức. | “No further maintenance releases after this date.” |

Các khái niệm trên liên quan nhưng không đồng nhất. Dự án có thể dùng JDK 21 để build một thư viện tương thích Java 17 bằng compiler --release 17. Ngược lại, việc build bằng JDK 17 không chứng minh thư viện đã kiểm thử trên mọi bản phân phối hoặc mọi môi trường chạy Java 17.

### 2.3. Java version không đồng nghĩa với product version

Hai lịch phát hành phải được diễn giải riêng:

1. **Java/JDK version:** chẳng hạn Java 17 hoặc Java 21, kèm nhà cung cấp và mức bản vá.
2. **Phiên bản sản phẩm:** chẳng hạn library 2.x hoặc 3.x, có chính sách hỗ trợ và lịch bảo trì riêng.

Khi viết “ngừng hỗ trợ Java 17”, cần nêu rõ áp dụng cho **phiên bản sản phẩm nào**. Một bản phát hành 3.x có thể yêu cầu Java 21, trong khi nhánh 2.x vẫn nhận bản vá tương thích Java 17 cho đến thời điểm đã công bố.

Nếu không phân biệt hai lịch, người dùng có thể hiểu nhầm rằng Java 17 ngừng tồn tại hoặc mọi sản phẩm của tổ chức đều dừng hỗ trợ Java 17 cùng một ngày.

## 3. Vì sao công bố mức Java tối thiểu là thay đổi API?

Ở góc độ thư viện, mức Java tối thiểu là một phần điều kiện tiêu thụ artifact.

Khi nâng mức tối thiểu:

- Class file có thể được tạo với version bytecode mà JVM cũ không đọc được.
- Source code có thể sử dụng API JDK chỉ tồn tại ở Java mới.
- Dependency và framework mới có thể đã nâng minimum Java version.
- Plugin hoặc agent runtime có thể yêu cầu JDK khác trước.
- Một số API bị loại bỏ hoặc thay đổi hành vi, buộc consumer sửa mã hoặc cấu hình.
- Việc chuyển đổi có thể làm thay đổi cách đóng gói module, classpath, module path và hoạt động của reflection.

Đối với thư viện dùng chung, thay đổi này có thể là **breaking change** dù mọi public method vẫn giữ nguyên signature. Consumer dùng Java cũ không thể chạy artifact mới nếu bytecode hoặc dependency yêu cầu Java mới.

Ví dụ, một class được biên dịch cho Java 21 có class-file major version 65, trong khi JVM Java 17 chỉ hỗ trợ class-file version đến 61. Chạy artifact đó trên Java 17 có thể dẫn đến UnsupportedClassVersionError trước khi ứng dụng thực hiện được nghiệp vụ.

Không nên chỉ so sánh code API public để kết luận thay đổi hỗ trợ JDK có tương thích ngược. Môi trường tối thiểu được yêu cầu để chạy một artifact là một phần thực tế của contract phát hành.

## 4. Xác định Java tối thiểu bằng bằng chứng kỹ thuật

Trước khi công bố, cần phân biệt **mức mong muốn**, **mức được cấu hình** và **mức đã xác minh**.

### 4.1. Kiểm kê các ràng buộc

Một bản kiểm kê nên thu thập:

| Thành phần | Câu hỏi chính | Bằng chứng |
|---|---|---|
| Source code | Mã có dùng cú pháp/ngôn ngữ chỉ hỗ trợ ở release mới không? | Compiler settings và build từ source. |
| Java API | Có gọi API JDK chưa tồn tại trong mức Java tối thiểu được đề xuất không? | Compile với --release và phân tích API. |
| Class file | Bytecode được phát hành nhắm tới phiên bản JVM nào? | Compiler target và javap -verbose. |
| Dependency trực tiếp | Mỗi thư viện yêu cầu Java tối thiểu nào? | Release notes, metadata, kiểm tra class file và test. |
| Dependency bắc cầu | Có thư viện kéo vào JAR chỉ chạy trên Java mới hơn không? | Dependency graph/runtime classpath. |
| Framework | Bản framework được chọn có yêu cầu Java mới không? | Compatibility matrix và tài liệu phát hành. |
| Build tool / plugin | Gradle, Maven, plugin và annotation processor dùng JDK nào? | Wrapper, toolchain và CI log. |
| Runtime | Host/container/application server đang thực thi Java nào? | java -version, image digest, process runtime. |
| Consumer | Các ứng dụng khách đang dùng Java và phiên bản thư viện nào? | Inventory, feedback, telemetry phù hợp. |

Nếu bản thân thư viện chạy được trên Java 17 nhưng một dependency runtime bắt buộc Java 21, mức tối thiểu thực tế của tổ hợp sản phẩm không thể được công bố là Java 17 mà không thay dependency hoặc cung cấp cấu hình tương thích.

### 4.2. Đọc bytecode target

Có thể dùng javap để xem major version của class file:

~~~bash
javap -verbose -classpath my-library.jar com.example.LibraryEntry
~~~

Trong output, tìm major version. Ví dụ phổ biến:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Kiểm tra một class file là thông tin tham khảo, không đủ để chứng minh toàn bộ JAR tương thích; các class khác và dependency có thể có bytecode cao hơn.

### 4.3. Không chỉ hạ target bytecode

Nếu dùng javac hiện đại, nên cân nhắc tùy chọn --release khi cần tạo artifact tương thích Java cũ. Tùy chọn này giới hạn ngôn ngữ, bytecode và API nền tảng khả dụng ở release được chọn.

Ví dụ:

~~~bash
javac --release 17 -d out src/main/java/com/example/LibraryEntry.java
~~~

Nếu chỉ hạ target bytecode nhưng vẫn compile với API chỉ có ở JDK mới, code có thể biên dịch thành công nhưng gặp NoSuchMethodError hoặc NoClassDefFoundError trên runtime cũ. --release giảm nguy cơ đó trong phạm vi API nền tảng do compiler kiểm soát.

Tuy nhiên, --release không tự xác minh dependency bên thứ ba, reflection, mã native, optional module, service provider hoặc hành vi runtime. Bước xác nhận cuối vẫn cần chạy test bằng đúng Java tối thiểu đã công bố.

### 4.4. Mức tối thiểu của ứng dụng và thư viện có thể khác nhau

Ví dụ:

~~~text
Library core     : minimum Java 17
CLI distribution : minimum Java 21
Server runtime   : minimum Java 21
Build pipeline   : JDK 21
~~~

Đây có thể là cấu hình hợp lệ nếu sản phẩm công bố từng artifact riêng. Nếu đóng gói chung mà không làm rõ, consumer có thể hiểu nhầm mọi artifact đều tương thích Java 17.

Vì vậy, chính sách cần gắn yêu cầu Java với đúng artifact, module hoặc deployment target thay vì chỉ một nhãn chung cho toàn bộ repository.

## 5. Thiết kế chính sách hỗ trợ Java

### 5.1. Xác định phạm vi trách nhiệm

Trước khi thông báo ngày ngừng hỗ trợ, nhóm sản phẩm cần quyết định các phạm vi sau:

- Dòng sản phẩm nào được hỗ trợ trên mỗi Java release?
- Có hỗ trợ mọi bản phân phối OpenJDK hay chỉ một tập hợp đã kiểm thử?
- Có yêu cầu các bản vá bảo mật mới nhất trong cùng major release không?
- Các hệ điều hành, kiến trúc CPU và container image nào nằm trong phạm vi hỗ trợ?
- Bản patch/minor của dòng cũ có nhận bugfix, security fix hay chỉ hỗ trợ theo mức best effort?
- Ngày nào dừng tính năng mới, ngày nào dừng bugfix thông thường, ngày nào dừng hỗ trợ hoàn toàn?
- Có trường hợp ngoại lệ thương mại hoặc hợp đồng hỗ trợ mở rộng không?

Không nên hứa “hỗ trợ Java 17, 21 và mọi JDK mới” nếu CI chỉ kiểm tra Java 21. Định nghĩa hỗ trợ phải đi kèm cam kết cụ thể về test, xử lý lỗi và cập nhật bảo mật.

### 5.2. Ma trận hỗ trợ minh họa

Bảng sau là **tình huống giả định**, không phải lịch hỗ trợ thực tế của bất kỳ dự án nào:

| Dòng sản phẩm | Java tối thiểu | Java được xác nhận trong CI | Trạng thái hỗ trợ | Chính sách thay đổi |
|---|---:|---|---|---|
| Library 2.x | 17 | 17 và 21 | Maintenance đến hạn công bố | Chỉ nhận sửa lỗi phù hợp chính sách; không bổ sung API yêu cầu Java 21. |
| Library 3.x | 21 | 21 | Active | Có thể sử dụng Java 21 và dependency/framework yêu cầu mức Java tương ứng. |
| Library 1.x | Theo thông báo phát hành trước | Không còn trong matrix hiện hành | End of life theo chính sách riêng | Không hứa phát hành bản vá mới. |

Lưu ý:

- “Minimum 17” không tự động nghĩa là mọi Java 18, 19, 20 hay Java tương lai đều được kiểm thử.
- “Supported 17 và 21” cho biết hai mức mà tổ chức tuyên bố hỗ trợ theo phạm vi ma trận; cần diễn giải riêng các release khác.
- Một JDK vendor hoặc bản update có thể ảnh hưởng đến độ tin cậy. Cần xác định phạm vi hỗ trợ bản phân phối khi cần.
- Các phiên bản sản phẩm khác nhau có thể hỗ trợ Java khác nhau trong một khoảng thời gian.

### 5.3. Chế độ hỗ trợ

Một sản phẩm có thể dùng các mức:

**Active support:** nhận phát triển, hỗ trợ chức năng, sửa lỗi và bản vá theo lịch.

**Maintenance support:** tiếp tục nhận một tập con sửa lỗi, thường tập trung vào lỗi nghiêm trọng và bảo mật; không hứa tính năng mới.

**Extended support (nếu có):** hỗ trợ có điều kiện cho consumer cần thêm thời gian. Phải công bố phạm vi, mốc thời gian và cách đăng ký thay vì mặc định mọi khách hàng đều được hưởng.

**End of life (EOL):** không còn phát hành hoặc hỗ trợ theo phạm vi đã định nghĩa. EOL không khiến artifact cũ lập tức ngừng chạy, nhưng tổ chức không còn cam kết kiểm thử, hỗ trợ hoặc phát hành bản vá cho nó.

Các nhãn Active, Maintenance, Extended và EOL cần có định nghĩa chính thức của tổ chức. Không nên dùng cùng một từ “ngừng hỗ trợ” để chỉ cả việc dừng tính năng mới lẫn dừng mọi bản vá.

## 6. Xây dựng mốc thông báo và ngừng hỗ trợ

Một chính sách tốt không chỉ nêu ngày kết thúc, mà phải cho consumer đủ thông tin và thời gian chuyển đổi.

### 6.1. Các mốc thời gian

| Mốc | Ý nghĩa | Nội dung nên thông báo |
|---|---|---|
| Announcement date | Công bố định hướng nâng Java tối thiểu. | Phiên bản Java cũ/mới, dòng sản phẩm liên quan, lý do và liên hệ. |
| Deprecation / transition period | Giai đoạn khuyến cáo chuyển và duy trì API/dòng cũ. | Hướng dẫn migration, test matrix, các điểm tương thích cần sửa. |
| Preview / release candidate | Cho consumer thử bản yêu cầu Java mới trước GA. | Cách tải bản thử, điều kiện test và phản hồi. |
| GA of new major | Phát hành dòng sản phẩm mới với mức Java tối thiểu mới. | Release notes, requirements, breaking changes và rollback. |
| End of regular maintenance | Dừng bảo trì thông thường cho nhánh hỗ trợ Java cũ. | Loại sửa lỗi vẫn nhận, nếu có, và thời hạn cuối. |
| EOL of old line | Dừng các cam kết hỗ trợ còn lại cho dòng cũ. | Chính sách bản vá, bảo mật, tài liệu lưu trữ và lựa chọn nâng cấp. |

### 6.2. Ví dụ thông báo có ngày cụ thể

Giả sử một thư viện hiện có dòng 2.x yêu cầu Java 17 và muốn phát hành dòng 3.x yêu cầu Java 21. Một lịch giả định có thể như sau:

| Ngày (minh họa) | Sự kiện |
|---|---|
| 01/02/2027 | Công bố kế hoạch: Library 3.x sẽ yêu cầu Java 21; Library 2.x tiếp tục hỗ trợ Java 17 theo thời hạn. |
| 01/05/2027 | Phát hành preview của Library 3.x và mở đợt thử nghiệm cho consumer. |
| 01/08/2027 | Library 3.0 GA với mức runtime tối thiểu Java 21. |
| 31/12/2027 | Ngày cuối của maintenance support cho Library 2.x theo chính sách giả định. |
| 01/01/2028 | Library 2.x chuyển sang EOL; không hứa phát hành bản vá mới. |

**Đây là lịch minh họa để giải thích cách công bố; không phải lịch hỗ trợ thực tế của Java, JDK vendor hay sản phẩm bất kỳ.** Khi áp dụng, ngày phải được chủ sở hữu sản phẩm phê duyệt, cân nhắc vòng phát hành, yêu cầu bảo mật, thời gian kiểm thử và hợp đồng với consumer.

Thông báo nên sử dụng ngày cụ thể kèm múi giờ nếu mốc có tính hiệu lực vận hành. Tránh “tháng sau”, “quý tới” hoặc “sẽ sớm dừng hỗ trợ” trong release notes chính thức vì những cụm từ đó trở nên mơ hồ sau một thời gian.

### 6.3. Không trộn lẫn EOL của JDK vendor với EOL của sản phẩm

Các nhà cung cấp JDK có vòng đời bảo trì riêng cho từng bản phân phối và hình thức hỗ trợ. Tổ chức phát triển thư viện có thể ngừng hỗ trợ một Java release trước hoặc sau mốc bảo trì của một nhà cung cấp JDK cụ thể, tùy chính sách và nghĩa vụ của mình.

Vì vậy, không được viết “Java 17 EOL vào ngày X” chỉ vì **sản phẩm của mình** dừng hỗ trợ Java 17 vào ngày đó. Nên viết rõ:

> “Từ ngày X, nhánh Library 2.x của chúng tôi ngừng nhận bản vá bảo trì cho môi trường Java 17.”

Nếu cần viện dẫn lịch hỗ trợ JDK từ nhà cung cấp, phải ghi rõ vendor, bản phân phối, mô hình hỗ trợ và nguồn tài liệu cập nhật tại thời điểm công bố.

## 7. Liên kết chính sách Java với versioning của sản phẩm

Nâng Java tối thiểu có thể làm hỏng khả năng chạy của consumer dù API public giữ nguyên. Trong thư viện công bố theo Semantic Versioning, đây thường là thay đổi đáng cân nhắc cho một major release.

Ví dụ:

~~~text
2.8.x: minimum Java 17, maintenance branch
3.0.0: minimum Java 21, new active branch
~~~

Lưu ý, SemVer là quy ước truyền đạt mức tương thích, không tự tạo tương thích nhị phân. Nếu consumer dùng Java 17 tải 3.0.0, nhãn “3.0.0” không giúp JVM Java 17 đọc bytecode Java 21.

Một chính sách phát hành cần phân biệt:

- Major release: thay đổi có khả năng phá vỡ contract đã công bố, bao gồm mức runtime bắt buộc khi áp dụng.
- Minor release: tính năng mới nhưng vẫn giữ mức tương thích mà nhánh đã cam kết.
- Patch release: sửa lỗi/bảo mật không tự ý nâng minimum Java trong nhánh được tuyên bố tương thích.

Không nhất thiết mọi dự án đều dùng SemVer. Dù chọn mô hình versioning khác, nguyên tắc là **mỗi artifact phải có yêu cầu Java rõ ràng và người dùng phải nhận biết được breaking change trước khi nâng phiên bản**.

### 7.1. Hỗ trợ đồng thời nhiều nhánh

Một dự án có thể bảo trì hai nhánh trong giai đoạn chuyển tiếp:

~~~text
release/2.x  ── Java 17 baseline ── bugfix/security maintenance ── EOL
release/3.x  ── Java 21 baseline ── feature + maintenance ────────>
~~~

Với mô hình này, phải phân công chủ sở hữu và tiêu chí backport. Nếu một bản vá bảo mật được sửa ở 3.x nhưng 2.x còn hỗ trợ, nhóm cần đánh giá khả năng backport mà không đưa API Java 21 vào code Java 17.

Backport có thể cần implementation khác nhau vì Java API, framework hoặc dependency trên hai nhánh khác nhau. Không nên cherry-pick mù quáng rồi chỉ kiểm tra build trên JDK mới.

### 7.2. Khi không thể duy trì hai nhánh

Nếu nguồn lực không đủ, có thể quyết định chỉ duy trì một nhánh, nhưng thời gian thông báo cần phản ánh rủi ro đối với consumer. Các lựa chọn có thể gồm:

- Kéo dài thời gian trước ngày EOL.
- Cung cấp bản chuyển tiếp tương thích để consumer giảm số bước nâng cấp.
- Phát hành migration guide và công cụ kiểm tra cấu hình.
- Cho phép support có điều kiện, có giới hạn và chủ sở hữu cụ thể.
- Công bố rõ khả năng không còn vá lỗi bảo mật trên nhánh cũ.

Không nên duy trì một lời hứa hỗ trợ mà nhóm không có khả năng thực hiện, đặc biệt với sự cố bảo mật và vận hành production.

## 8. Cấu hình build để phản ánh mức Java công bố

Chính sách trên giấy phải nhất quán với artifact build và CI.

### 8.1. Gradle: JDK biên dịch và release target

Ví dụ một thư viện tiếp tục hỗ trợ runtime Java 17 nhưng build tool chạy trên JDK 21. Với Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Ý nghĩa:

- Gradle tìm compiler Java 21 theo cấu hình toolchain.
- --release 17 giới hạn ngôn ngữ, class-file target và API JDK cho mã được biên dịch.
- Điều này **chưa đủ** để khẳng định toàn bộ runtime dependencies tương thích Java 17.

Trong nhánh 3.x yêu cầu Java 21, có thể nâng release target thành 21:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
~~~

Đây là ví dụ dành cho Java plugin và compilation task tương ứng. Dự án hỗn hợp Kotlin/Scala/Groovy hoặc tạo mã bằng annotation processor có thể cần cấu hình và kiểm tra thêm cho từng loại artifact.

### 8.2. Maven: compiler release

Với Maven, một cách khai báo mức release:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Khi chính sách Java tối thiểu đổi sang 21 cho nhánh mới, cấu hình tương ứng có thể là:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

Compiler plugin và JDK/toolchain phải hỗ trợ release được chọn. Maven đang được khởi chạy bằng một JDK không nhất thiết sử dụng chính JDK đó để compile nếu dự án có Maven Toolchains hoặc compiler fork.

Lưu ý không nên dùng một build JDK mới rồi giả định runtime cũ luôn tương thích chỉ vì source/target được đặt về giá trị cũ. Mức release và các dependency thực tế mới là thông tin cần đối chiếu.

### 8.3. Compiler release là điều kiện cần, không phải điều kiện đủ

Hãy bổ sung kiểm tra:

1. Class file trong artifact, không chỉ class chính.
2. Runtime dependencies và phần đóng gói fat/uber JAR.
3. Code sinh tự động và mã trong module được build riêng.
4. Các class trong multi-release JAR nếu sử dụng.
5. Reflection, native binding, service loader và integration của framework.
6. Test runtime bằng Java thấp nhất được công bố.

Một multi-release JAR có thể chứa class version-specific dưới META-INF/versions. Nếu dùng kỹ thuật này, phần base phải tuân thủ mức Java tối thiểu, và behavior trên từng Java release cần được kiểm thử. Đó là cơ chế có điều kiện, không phải cách tự động hỗ trợ mọi JDK.

## 9. Thiết kế CI matrix cho chính sách hỗ trợ

Mức Java tối thiểu chỉ đáng tin cậy khi được kiểm chứng ở pipeline có thể tái lập.

### 9.1. Các mức nên kiểm tra

Với một thư viện công bố hỗ trợ Java 17 và Java 21, CI có thể tách:

- Build artifact theo release target 17.
- Unit/integration tests chạy trên Java 17.
- Unit/integration tests chạy trên Java 21.
- Test với dependency/framework versions được hỗ trợ.
- Binary compatibility tests đối với thư viện đã phát hành, nếu có cam kết hỗ trợ binary client cũ.

Ở nhánh 3.x yêu cầu Java 21, CI tối thiểu cần chạy trên Java 21. Nếu muốn công bố hỗ trợ thêm Java release khác, đưa release đó vào matrix với mức kiểm thử phù hợp và công bố giới hạn nếu khác.

### 9.2. Ví dụ CI theo ý tưởng chung

~~~yaml
strategy:
  matrix:
    java: ["17", "21"]

steps:
  - name: Select Java
    # Sử dụng bước setup JDK phù hợp với nền tảng CI.
    # Distribution và version lấy từ matrix.
  - name: Record runtime version
    run: java -version
  - name: Run tests
    run: ./gradlew test
~~~

Đây là **khung minh họa**, không phải workflow hoàn chỉnh có thể chạy nguyên văn. Trong CI thật cần thêm checkout source, bước cài JDK cụ thể, wrapper executable permission, cache phù hợp và điều kiện chạy trên từng hệ điều hành.

Điều quan trọng là lệnh java -version và JVM thực thi test phải phản ánh Java của ô matrix. Với Gradle, nếu test task dùng toolchain khác với JDK runner, cần xác nhận launcher thực tế. Tương tự với Maven Surefire/Failsafe khi có cấu hình fork hoặc toolchains.

### 9.3. Kiểm tra khả năng sử dụng từ consumer

Ngoài test nội bộ của thư viện, tạo một client fixture đơn giản:

1. Build thư viện bằng cấu hình release hiện hành.
2. Đưa artifact vào một ứng dụng khách độc lập.
3. Biên dịch và chạy ứng dụng khách với Java tối thiểu.
4. Thực hiện đường API công bố và kiểm tra hành vi.
5. Nếu là migration có cam kết tương thích nhị phân, chạy binary client cũ mà không biên dịch lại.

Nếu chỉ build và test mọi thứ bằng JDK 21, lỗi tương thích Java 17 có thể bị bỏ sót. Một release target 17 cũng không chứng minh app server, container và dependency hoạt động trên JDK 17.

### 9.4. Theo dõi lỗi sớm

Một số tín hiệu thường gặp:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| UnsupportedClassVersionError | Artifact hoặc dependency được compile cho Java mới hơn runtime. | Kiểm tra major version, JDK runtime và mức release được build. |
| NoSuchMethodError / NoClassDefFoundError | Lệch version dependency hoặc gọi API không có trong runtime. | Xem runtime classpath, dependency tree và API target. |
| InaccessibleObjectException | Reflection bị hạn chế bởi ranh giới module/encapsulation. | Nâng dependency/framework và kiểm tra hướng migration phù hợp. |
| Test chỉ lỗi trên JDK tối thiểu | Có API mới, behavior khác, agent hoặc native dependency không tương thích. | Chạy lại ở môi trường tối thiểu, xác định nguồn khác biệt. |
| Chạy local được, production lỗi | Image/runtime triển khai khác JDK đã test. | Ghi rõ image digest, java -version và command thực thi. |

Những lỗi này là gợi ý điều tra, không phải chẩn đoán duy nhất. Cần kiểm tra stack trace và artifact thực tế trước khi kết luận.

## 10. Công bố thông tin tại những điểm consumer dễ tìm

Chính sách Java tối thiểu phải có một nguồn chính thức và được lặp lại đúng ở những nơi consumer ra quyết định nâng cấp.

### 10.1. README hoặc trang System Requirements

Nên có một đoạn dễ nhận thấy:

~~~text
System requirements

Product 3.x:
  Minimum Java runtime: 21
  Java versions validated in CI: 21
  Recommended: current security-patched Java 21 distribution

Product 2.x:
  Minimum Java runtime: 17
  Java versions validated in CI: 17 and 21
  Maintenance support ends: 31 Dec 2027 (illustrative only)
  EOL: 01 Jan 2028 (illustrative only)
~~~

Các ngày trong ví dụ chỉ là dữ liệu minh họa. README thật cần ngày và phạm vi đã được phê duyệt, cùng link đến migration guide.

### 10.2. Release notes và changelog

Đặt breaking requirement ngay đầu release notes, không giấu trong danh sách thay đổi:

> **Breaking requirement:** Product 3.0 requires Java 21 at runtime. Consumers running on Java 17 must remain on the supported 2.x line until they can migrate. See the support matrix and migration guide for dates and steps.

Nên ghi thêm lý do nâng mức tối thiểu, những tính năng/dependency thúc đẩy thay đổi và các giới hạn cần chú ý như framework, database driver hoặc container image.

### 10.3. Dependency metadata và hệ sinh thái phân phối

Với một số hệ sinh thái, metadata của artifact hoặc cơ chế resolve dependency có thể giúp toolchain nhận diện yêu cầu tương thích. Tuy nhiên, không nên giả định metadata JAR/Maven POM luôn có trường chuẩn, được mọi client kiểm tra, để ngăn việc dùng sai Java release.

Một số thông tin manifest mô tả JDK đã build artifact, nhưng không nhất thiết là minimum runtime requirement. Vì vậy, tài liệu support matrix và test trên JDK tối thiểu vẫn là nguồn cam kết cần duy trì.

Nếu có quy tắc nội bộ để chặn dependency không tương thích, hãy ghi rõ cơ chế và phạm vi công cụ. Không tuyên bố “build tool tự động chặn Java cũ” nếu thực tế resolver vẫn cho phép tải JAR rồi chỉ lỗi ở runtime.

### 10.4. Các kênh cần đồng bộ

- README / trang yêu cầu hệ thống.
- Compatibility matrix và support policy.
- Release notes, changelog và thông báo major version.
- Migration guide / upgrade guide.
- Tài liệu Docker image, Helm chart hoặc deployment template.
- SDK/client documentation và trang tải artifact.
- Issue tracker, kênh thông báo cho nhóm tích hợp và đối tác có liên quan.

Mỗi kênh nên dẫn về một nguồn chính thức để tránh có tài liệu ghi “Java 17 được hỗ trợ” trong khi release notes mới đã chuyển sang “minimum Java 21”.

## 11. Hướng dẫn dành cho consumer trước ngày ngừng hỗ trợ

Thông báo chỉ có ích nếu người dùng biết hành động cụ thể phải thực hiện.

### 11.1. Kiểm kê runtime thực tế

Consumer cần xác định:

- Java version trong terminal, IDE, CI runner, build container và runtime deployment.
- Base image hiện tại và JDK/JRE thực sự dùng để chạy process.
- Version thư viện/framework và danh sách dependency kéo theo.
- Các batch job/plugin hoặc service được triển khai tách biệt.
- Lịch thay đổi và quyền nâng JDK ở môi trường production.

Không nên chỉ dựa vào JAVA_HOME trên máy phát triển để kết luận production đã đáp ứng mức Java mới.

### 11.2. Thử nâng trong môi trường tách biệt

Quy trình cho consumer có thể là:

1. Chạy ứng dụng hiện tại trên Java mục tiêu, khi sản phẩm hiện tại có hỗ trợ việc đó.
2. Nâng dependency và framework có yêu cầu đi kèm.
3. Biên dịch lại nếu API mới có breaking source changes.
4. Chạy unit test, integration test, regression test và kiểm thử dữ liệu.
5. Kiểm tra TLS, locale, charset, timezone, reflection, serialization và hiệu năng.
6. Nâng image/container/CI theo cùng cấu hình đã kiểm thử.
7. Triển khai canary hoặc rollout theo giai đoạn, theo dõi lỗi và latency.
8. Giữ kế hoạch rollback phù hợp với thay đổi schema và dữ liệu.

Nâng JDK build và runtime có thể được tách thành các bước nếu mức release và dependency cho phép. Cần kiểm chứng từng bước thay vì nâng tất cả cùng lúc mà không có mốc đối chiếu.

### 11.3. Consumer chưa thể nâng

Nếu hệ thống vẫn phụ thuộc Java cũ vì framework, vendor software hoặc giới hạn hạ tầng, consumer cần được hướng dẫn:

- Tiếp tục dùng nhánh sản phẩm nào còn maintenance.
- Bản vá nào còn được cung cấp và đến thời điểm nào.
- Làm sao báo cáo lỗi/bảo mật trong thời gian chuyển tiếp.
- Có lựa chọn extended support, adapter hay phiên bản LTS nội bộ nào không, nếu chính sách cho phép.
- Những rủi ro vận hành và bảo mật phải chấp nhận nếu quá hạn EOL.

Không nên chỉ ghi “nâng ngay lên Java mới” mà không nói rõ phương án hợp lệ trong khoảng thời gian chuyển tiếp, nhất là đối với hệ thống có chu kỳ phát hành dài.

## 12. Mẫu thông báo chính thức

Dưới đây là **mẫu nội dung minh họa** để điều chỉnh theo lịch và phiên bản thực tế.

### Thông báo nâng Java tối thiểu

~~~markdown
# Notice: Java baseline change in Product 3.0

Starting with Product 3.0, the minimum runtime requirement is Java 21.
Product 2.x remains the supported maintenance line for Java 17 until
31 December 2027. Product 2.x reaches EOL on 1 January 2028.

Impact:
- Applications running Product 3.0 on Java 17 are not supported.
- Consumers using Java 17 should continue on an eligible Product 2.x
  maintenance release until their migration is ready.
- Applications upgrading to Product 3.0 should validate runtime,
  dependencies, framework and deployment images on Java 21.

Action required:
1. Inventory Java versions in developer, CI and runtime environments.
2. Run the migration test matrix on Java 21.
3. Update build toolchains and deployment images.
4. Upgrade Product dependencies and verify API compatibility.
5. Complete rollout before the published maintenance EOL.

See:
- Compatibility matrix
- Migration guide from 2.x to 3.x
- Release notes for Product 3.0
- Support contact / issue tracker

Dates above are illustrative; use approved product dates when publishing.
~~~

Trong môi trường thực tế có thể viết bằng tiếng Việt và thay Product bằng tên dự án. Điều quan trọng là tiêu đề, tác động, hành động, mốc thời gian và đường dẫn tài liệu đều hiện diện.

### 12.1. Thông báo thay đổi ngày EOL

Nếu phải thay đổi mốc EOL, không nên chỉ sửa lặng lẽ một ngày trong README.

Cần thông báo:

- Mốc cũ và mốc mới.
- Phạm vi nhánh và Java release bị ảnh hưởng.
- Lý do thay đổi và mức hỗ trợ trong thời gian bổ sung/rút ngắn.
- Consumer nào cần hành động sớm hơn.
- Ngày công bố và người phê duyệt chính sách.

Nếu ngày EOL được rút ngắn, việc truyền thông phải tính đến thời gian chuẩn bị của consumer và cam kết đã ký. Không nên dùng thay đổi lịch như một cách gián tiếp buộc nâng cấp mà không có kế hoạch xử lý rủi ro.

## 13. Ngoại lệ và quản lý rủi ro bảo mật

Trong doanh nghiệp, một số ứng dụng không thể nâng JDK trước hạn vì phụ thuộc phần mềm bên thứ ba hoặc chu kỳ thay đổi được quản lý nghiêm ngặt. Ngoại lệ cần có giới hạn và trách nhiệm rõ ràng.

Một bản ghi ngoại lệ nên gồm:

| Trường | Nội dung |
|---|---|
| Consumer / workload | Service hoặc ứng dụng xin duy trì Java cũ. |
| Phiên bản hiện tại | Product version, Java version, JDK distribution và patch level. |
| Nguyên nhân chặn nâng | Framework, vendor SDK, hệ điều hành, hạ tầng hoặc ràng buộc khác. |
| Phạm vi hỗ trợ | Security fixes, critical bugfixes, best effort hay không hỗ trợ. |
| Chủ sở hữu | Nhóm chịu trách nhiệm migration và phê duyệt ngoại lệ. |
| Hạn ngoại lệ | Ngày kết thúc hiệu lực, không tự gia hạn. |
| Biện pháp giảm thiểu | Segmentation, giám sát, hạn chế quyền, kiểm soát kết nối hoặc biện pháp phù hợp khác. |
| Kế hoạch thoát | Các bước loại bỏ dependency chặn, nâng JDK và xác nhận lại. |

Một ngoại lệ không thể biến một runtime đã hết bản vá thành runtime an toàn chỉ bằng văn bản phê duyệt. Cần đánh giá riêng mức hỗ trợ bảo mật từ JDK vendor và các biện pháp bảo vệ vận hành.

### 13.1. Bảo mật và chi phí hỗ trợ

Khi quyết định duy trì Java cũ, nhóm sản phẩm cần đánh giá:

- Khả năng nhận security update cho runtime và dependency.
- Nỗ lực backport khi nhánh mới dùng API/framework không có trên Java cũ.
- Khả năng chạy lại CI, build reproducibility và kiểm thử trên runtime cũ.
- Rủi ro bảo mật hoặc vận hành nếu tiếp tục cung cấp patch cho nền tảng ít được thử nghiệm.
- Cam kết với khách hàng và các yêu cầu tuân thủ.

Chính sách EOL nên phản ánh rủi ro và nguồn lực thực tế, không chỉ theo sở thích kỹ thuật của nhóm phát triển.

## 14. Quản lý rollout và rollback khi tăng Java baseline

Việc công bố yêu cầu mới phải đi cùng khả năng triển khai an toàn.

### 14.1. Kiểm tra trước triển khai

Trước khi phát hành bản yêu cầu Java mới:

1. Xác nhận artifact build bằng đúng release target và dependency graph.
2. Chạy test trên Java tối thiểu của dòng sản phẩm mới.
3. Kiểm tra Docker base image hoặc runtime provisioned trên host.
4. Kiểm tra startup flags, GC, agent, native library, TLS và reflection.
5. Đánh giá tương thích dữ liệu và giao thức với các service chưa nâng.
6. Chuẩn bị rollback ở cấp artifact/image, không chỉ sửa biến JAVA_HOME.
7. Kiểm tra tài liệu và release notes nêu rõ breaking requirement.

### 14.2. Không giả định rollback runtime là rollback toàn bộ thay đổi

Rollback sang artifact cũ có thể không thành công nếu schema database, event hoặc dữ liệu đã thay đổi. Ngược lại, chỉ chạy lại image cũ với JDK mới cũng có thể không được hỗ trợ.

Phải xác định trước tổ hợp artifact + JDK + dependency + configuration nào được phép khi rollback. Nếu cần hỗ trợ blue/green hoặc canary, các dịch vụ đang chạy ở hai Java release cần giao tiếp qua hợp đồng dữ liệu tương thích trong suốt giai đoạn chuyển tiếp.

### 14.3. Đo lường tiến độ migration

Nhóm sản phẩm nên theo dõi:

- Tỷ lệ consumer đã nâng lên Java tối thiểu mới.
- Tỷ lệ production workload vẫn chạy trên Java cũ, khi có nguồn đo hợp lệ.
- Số consumer còn phụ thuộc phiên bản sản phẩm maintenance.
- Kết quả CI trên Java tối thiểu và các Java release được hỗ trợ.
- Số blocker về framework/dependency/native library.
- Ngoại lệ còn hiệu lực và hạn hoàn thành của từng trường hợp.
- Số lỗi sau rollout liên quan JDK/dependency.

Không nên thu thập thông tin cá nhân hoặc bí mật cấu hình không cần thiết. Với thư viện phân phối cho bên ngoài, telemetry thường không đầy đủ; cần kết hợp khảo sát consumer, issue tracker và feedback từ nhóm tích hợp thay vì coi “không thấy lượt sử dụng” là bằng chứng chắc chắn không còn khách hàng.

## 15. Các lỗi truyền thông thường gặp

| Cách làm chưa phù hợp | Rủi ro | Cách công bố tốt hơn |
|---|---|---|
| “Nâng lên Java 21.” | Không rõ build JDK hay runtime JDK, áp dụng từ sản phẩm nào. | Ghi minimum runtime, build requirement và dòng sản phẩm áp dụng. |
| “Hỗ trợ Java 17+.” | Dễ bị hiểu là hỗ trợ mọi Java release về sau. | Ghi minimum required và danh sách Java release được kiểm thử/hỗ trợ. |
| “Java 17 ngừng hỗ trợ ngày X.” | Nhầm chính sách sản phẩm với lifecycle của nhà cung cấp JDK. | Ghi rõ nhánh sản phẩm nào dừng hỗ trợ Java 17 vào ngày X. |
| Dừng vá nhánh cũ ngay khi bản mới GA. | Consumer chưa kịp nâng, rủi ro bảo mật và vận hành. | Công bố maintenance window và EOL trước khi GA nếu có thể. |
| Đưa thay đổi runtime vào patch release im lặng. | Client bị lỗi ngoài dự đoán khi update dependency. | Chọn versioning và release notes thể hiện breaking requirement. |
| Chỉ đặt compiler target thấp. | Dependency có thể vẫn dùng bytecode/API mới. | Kiểm tra artifact/dependency và chạy test trên JDK tối thiểu. |
| Chỉ test JDK mới nhất. | Không phát hiện regression trên Java được công bố là tối thiểu. | Bắt buộc test runtime minimum trong CI. |
| Tài liệu README và changelog ghi khác nhau. | Consumer không biết nguồn nào chính xác. | Giữ support matrix là nguồn chuẩn, đồng bộ các kênh. |
| Không nêu timezone hoặc ngày hiệu lực. | Mơ hồ về hạn hỗ trợ và lịch triển khai. | Dùng ngày cụ thể, timezone nếu liên quan và mô tả loại hỗ trợ. |
| Cho phép ngoại lệ không có hạn. | Nhánh cũ tiếp tục tồn tại vô thời hạn. | Gắn owner, hạn, mức hỗ trợ, giảm thiểu và kế hoạch thoát. |

## 16. Bộ tài liệu cần đi kèm mỗi lần nâng Java tối thiểu

Đối với một thay đổi Java baseline có tác động đến consumer, gói công bố nên bao gồm:

1. **Support matrix:** phiên bản sản phẩm, Java tối thiểu, release được kiểm thử, trạng thái hỗ trợ.
2. **Release notes:** breaking requirement và lý do nâng mức Java.
3. **Migration guide:** các bước nâng JDK, dependency, build tool, framework và deployment.
4. **Lifecycle notice:** ngày thông báo, ngày GA, maintenance end và EOL của nhánh cũ.
5. **Compatibility evidence:** kết quả build/test trên Java tối thiểu, version toolchain và artifact identity.
6. **FAQ:** consumer còn dùng Java cũ phải làm gì, có thể trì hoãn đến bao giờ.
7. **Support route:** nơi gửi câu hỏi, cách báo lỗi và quy trình yêu cầu ngoại lệ.
8. **Ownership:** nhóm chịu trách nhiệm cập nhật lịch, phản hồi và xử lý thay đổi chính sách.

Điều kiện quan trọng là các tài liệu phải chỉ về cùng một chính sách, không tự mâu thuẫn. Nếu hỗ trợ Java 17 kết thúc ở nhánh 2.x vào một ngày đã công bố, không nên để tài liệu cũ tiếp tục khẳng định nhánh đó “fully supported” sau thời hạn.

## 17. Quy trình ra quyết định và công bố

Một quy trình thực tế có thể đi theo trình tự:

### Bước 1 — Đề xuất baseline mới

Nêu rõ vì sao cần nâng Java: dependency/framework mới yêu cầu, tính năng nền tảng, độ an toàn vận hành, chi phí bảo trì hay chiến lược chuẩn hóa công nghệ. Ghi phiên bản Java mục tiêu và những artifact bị ảnh hưởng.

### Bước 2 — Thu thập bằng chứng tương thích

Kiểm tra source, bytecode, API JDK, dependency, toolchain, CI và runtime. Xác định có cần nâng mức Java cho toàn bộ sản phẩm hay có thể giữ một artifact tương thích Java cũ.

### Bước 3 — Đánh giá consumer

Phân nhóm consumer theo mức Java hiện hành, khả năng nâng, chu kỳ phát hành và yêu cầu bảo mật. Xác định số lượng hệ thống ảnh hưởng và thời gian chuyển đổi tối thiểu.

### Bước 4 — Chọn chính sách versioning và hỗ trợ

Quyết định dòng sản phẩm nào mang baseline mới, nhánh nào nhận backport, ngày cuối bảo trì và EOL. Đặt chính sách ngoại lệ nếu cần, với phạm vi và chủ sở hữu rõ ràng.

### Bước 5 — Phê duyệt mốc thời gian

Đánh giá khả năng vận hành CI, năng lực hỗ trợ, hợp đồng và lịch triển khai của consumer. Không công bố ngày mà nhóm chưa có khả năng đáp ứng.

### Bước 6 — Xuất bản thông báo

Cập nhật support matrix, release notes, migration guide và kênh thông báo. Nêu chính xác version, minimum runtime, supported/tested releases và các ngày hiệu lực.

### Bước 7 — Triển khai và hỗ trợ chuyển đổi

Phát hành preview nếu cần, nhận feedback, xử lý blocker và kiểm thử trên JDK mục tiêu. Theo dõi consumer đang ở nhánh cũ và phân phối bản vá theo chính sách.

### Bước 8 — Xác nhận kết thúc hỗ trợ

Đến mốc đã công bố, cập nhật trạng thái nhánh cũ, giải quyết ngoại lệ, lưu trữ tài liệu phù hợp và nhắc consumer về các rủi ro còn lại. Nếu thay đổi lịch, phải ra thông báo chính thức thay vì chỉnh sửa thầm lặng.

## 18. Kết luận

Công bố mức Java tối thiểu và thời điểm ngừng hỗ trợ phiên bản cũ là một cam kết với consumer về **khả năng sử dụng artifact**, **phạm vi hỗ trợ** và **thời gian chuyển đổi**. Việc nâng baseline có thể phá vỡ tương thích thực tế dù chữ ký API Java không đổi, vì runtime, bytecode, dependency và framework là một phần của điều kiện chạy.

Một chính sách rõ ràng cần phân biệt mức Java bắt buộc, release đã kiểm thử, JDK build, bytecode target, nhánh sản phẩm đang được bảo trì và ngày EOL. Chính sách đó phải được xác minh bằng CI trên Java tối thiểu, thể hiện nhất quán trong support matrix, release notes và migration guide, đồng thời có lịch thông báo, kế hoạch hỗ trợ nhánh cũ và hướng xử lý consumer chưa nâng cấp.

Khi những thông tin này được công bố trước và theo dõi đến hết giai đoạn chuyển tiếp, nhóm có thể tiến hóa API và nền tảng Java có kiểm soát, còn consumer có đủ căn cứ để lên kế hoạch nâng cấp, kiểm thử, triển khai và quản lý rủi ro.
