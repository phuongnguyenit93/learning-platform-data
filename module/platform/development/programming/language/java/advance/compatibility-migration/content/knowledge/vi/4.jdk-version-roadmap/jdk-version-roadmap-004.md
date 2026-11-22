# Đọc release notes, migration guide và JEP liên quan

Khi chuẩn bị nâng cấp JDK, ba nguồn tài liệu cần đọc thường xuyên nhất là **release notes**, **migration guide** và **JEP (JDK Enhancement Proposal)**. Chúng bổ sung cho nhau: release notes mô tả những gì được phát hành trong một phiên bản hoặc bản cập nhật cụ thể; migration guide tập hợp các thay đổi có thể ảnh hưởng đến ứng dụng và hướng dẫn cách thích nghi; JEP giải thích mục tiêu, thiết kế và tác động của một cải tiến lớn trong OpenJDK.

Đọc đúng tài liệu giúp nhóm phát triển xác định thay đổi nào thực sự áp dụng cho đường nâng cấp của mình, thành phần nào có nguy cơ bị ảnh hưởng và cần kiểm chứng điều gì. Việc đọc không nên dừng ở danh sách tính năng mới. Những mục về hành vi mặc định, API bị loại bỏ, tùy chọn JVM, bảo mật, lỗi đã biết và vấn đề tương thích thường quyết định migration có an toàn hay không.

## 1. Vai trò của từng loại tài liệu

### 1.1. Release notes: phiên bản này đã thay đổi những gì?

Release notes là ghi chú phát hành cho một phiên bản JDK, một bản cập nhật hoặc một bản phân phối cụ thể. Tài liệu thường liệt kê các tính năng mới, thay đổi hành vi, lỗi đã sửa, vấn đề đã biết, thay đổi bảo mật và thông tin cài đặt hoặc vận hành.

Release notes giúp trả lời những câu hỏi như:

- Bản JDK mà nhóm định triển khai có những thay đổi nào?
- Có tùy chọn JVM, công cụ, API hoặc giá trị mặc định nào bị thay đổi không?
- Có lỗi đã biết nào liên quan đến hệ điều hành, kiến trúc, GC, TLS hoặc công cụ build không?
- Bản cập nhật có sửa lỗi bảo mật hoặc thay đổi chính sách bảo mật nào có thể ảnh hưởng kết nối hiện tại không?
- Có giới hạn hoặc lưu ý triển khai nào riêng cho bản phân phối đang sử dụng không?

Release notes có tính cụ thể theo phiên bản. Khi hai môi trường cùng ghi Java 21 nhưng dùng vendor, bản phân phối hoặc số build khác nhau, ghi chú phát hành có thể không hoàn toàn giống nhau. Vì thế, cần đọc đúng tài liệu của nhà cung cấp và đúng bản cập nhật dự kiến đưa lên production.

### 1.2. Migration guide: cần làm gì để chuyển ứng dụng?

Migration guide (hướng dẫn chuyển đổi) giải thích những thay đổi có thể phá vỡ giả định của ứng dụng khi chuyển từ một phiên bản Java sang phiên bản khác. Tài liệu thường gom các thay đổi theo chủ đề, mô tả tác động, cách nhận biết vấn đề và phương án điều chỉnh.

Migration guide thường hữu ích khi cần tìm:

- API, package hoặc module đã bị loại bỏ hay không còn được cung cấp mặc định.
- Thay đổi về module system, reflection và truy cập API nội bộ.
- Thay đổi trong compiler, bytecode, công cụ JDK hoặc tùy chọn JVM.
- Thay đổi về charset, locale, timezone, serialization và thư viện chuẩn.
- Thay đổi trong TLS, thuật toán mật mã, chứng chỉ và chính sách bảo mật.
- Các hành vi mặc định có thể làm ứng dụng cũ cho kết quả khác.
- Những bước kiểm tra hoặc cấu hình cần thực hiện trước khi triển khai.

Migration guide có góc nhìn chuyển đổi rộng hơn release notes. Nó có thể mô tả một thay đổi đã xuất hiện từ phiên bản trước đó, giải thích vì sao thay đổi quan trọng và gợi ý cách sửa ứng dụng. Tuy nhiên, không nên giả định mọi chi tiết của migration guide đều áp dụng cho mọi vendor hoặc mọi bản cập nhật. Hãy đối chiếu với release notes và tài liệu của đúng bản JDK đang sử dụng.

### 1.3. JEP: vì sao một thay đổi được thiết kế và nó tác động ra sao?

JEP là viết tắt của *JDK Enhancement Proposal*. Đây là tài liệu đề xuất và mô tả một cải tiến của JDK trong quy trình phát triển OpenJDK. Một JEP thường giải thích vấn đề cần giải quyết, mục tiêu, phạm vi, những điều không nằm trong phạm vi, thiết kế, phương án được cân nhắc và các tác động tương thích.

JEP hữu ích khi release notes chỉ nêu ngắn gọn tên tính năng hoặc thay đổi. Đọc JEP giúp hiểu:

- Vì sao thay đổi được đưa vào JDK.
- Tính năng giải quyết vấn đề nào và không nhằm giải quyết vấn đề nào.
- Thiết kế mới khác cách hoạt động cũ ở điểm nào.
- Những API, hành vi, công cụ hoặc cấu hình nào bị tác động.
- Có rủi ro tương thích, giới hạn hoặc phương án chuyển tiếp nào.
- Tính năng thuộc phiên bản nào và trạng thái triển khai ra sao.

JEP không phải là tài liệu thay thế release notes hoặc migration guide. Một JEP mô tả thiết kế và quá trình đưa cải tiến vào OpenJDK; release notes của bản JDK cụ thể mới giúp xác nhận những gì được phát hành trong bản đó. Ngoài ra, một thay đổi riêng của vendor hoặc bản phân phối có thể không có JEP tương ứng.

| Nguồn | Trọng tâm | Dùng khi cần trả lời |
|---|---|---|
| Release notes | Nội dung của bản phát hành cụ thể | Bản JDK này có gì mới, đã sửa gì, còn vấn đề gì? |
| Migration guide | Tác động và cách chuyển đổi ứng dụng | Ứng dụng cũ có thể bị ảnh hưởng ở đâu và cần thích nghi thế nào? |
| JEP | Mục tiêu, thiết kế và tác động của một cải tiến | Vì sao thay đổi được thực hiện, phạm vi của nó là gì và có rủi ro nào? |

## 2. Xác định đúng phiên bản và bản phân phối trước khi đọc

Tài liệu chỉ có giá trị khi khớp với môi trường thực tế. Trước khi mở release notes, hãy xác định rõ phiên bản hiện tại và phiên bản đích.

### 2.1. Ghi nhận JDK đang dùng ở cả build và runtime

Không nên chỉ nhìn phiên bản Java trong `build.gradle`, `pom.xml` hoặc README. Compiler dùng để build và JVM chạy ứng dụng có thể khác nhau. Hãy lấy thông tin từ môi trường thực tế.

Các lệnh cơ bản:

```bash
java -version
javac -version
```

Với Gradle, có thể xem JVM mà Gradle đang sử dụng:

```bash
./gradlew -version
```

Với Maven, cần kiểm tra cả Maven runtime và cấu hình compiler/toolchain của project. Trong môi trường container, hãy kiểm tra image và lệnh chạy bên trong container thay vì chỉ kiểm tra JDK cài trên máy phát triển.

Ngoài số phiên bản, hãy ghi nhận:

- Vendor và bản phân phối, ví dụ Oracle JDK, Eclipse Temurin, Amazon Corretto hoặc bản OpenJDK do hệ điều hành cung cấp.
- Phiên bản đầy đủ, số build và mức cập nhật bảo mật.
- JDK dùng để compile, test, chạy Gradle/Maven và chạy ứng dụng.
- Hệ điều hành, kiến trúc CPU và loại image container.
- JVM arguments, biến môi trường và các system properties quan trọng.

Một số thông tin có thể xem bằng:

```bash
java -XshowSettings:properties -version
```

Lệnh này in ra nhiều system properties, trong đó có các thông tin như vendor, runtime version, kiến trúc và charset mặc định. Cần lưu lại đúng output của môi trường build hoặc runtime đang điều tra.

### 2.2. Xác định đường nâng cấp

Hãy ghi rõ phiên bản nguồn và phiên bản đích, chẳng hạn Java 11 lên Java 21. Nếu đi qua nhiều phiên bản lớn, đừng chỉ đọc tài liệu của phiên bản đích. Những thay đổi được đưa vào ở các phiên bản trung gian vẫn có thể ảnh hưởng ứng dụng.

Ví dụ:

```text
JDK hiện tại: 11
       |
       v
Các thay đổi từ JDK 12, 13, 14, ...
       |
       v
JDK mục tiêu: 21
```

Không nhất thiết phải triển khai ứng dụng lần lượt trên mọi phiên bản trung gian. Tuy nhiên, khi nghiên cứu thay đổi, cần rà soát các phiên bản có liên quan trong khoảng nâng cấp để không bỏ sót API bị loại bỏ, thay đổi mặc định hoặc thay đổi bảo mật xuất hiện trước phiên bản đích.

### 2.3. Phân biệt phiên bản tính năng và bản cập nhật

Trong lịch phát hành hiện đại, một phiên bản tính năng như Java 21 có thể tiếp tục nhận nhiều bản cập nhật. Các bản cập nhật thường chứa sửa lỗi và bản vá bảo mật; chúng vẫn có thể thay đổi hành vi hoặc chính sách bảo mật có liên quan đến ứng dụng.

Vì vậy, ghi “nâng lên Java 21” có thể chưa đủ. Cần biết chính xác bản cập nhật, số build, vendor và image sẽ triển khai. Khi sự cố chỉ xuất hiện ở một môi trường, thông tin này giúp phân biệt khác biệt giữa các bản phân phối hoặc mức cập nhật.

## 3. Cách đọc release notes có hệ thống

Không nên chỉ lướt phần tính năng mới. Với mục tiêu migration, hãy đọc release notes theo thứ tự ưu tiên dựa trên khả năng ảnh hưởng đến ứng dụng.

### 3.1. Kiểm tra đúng tài liệu của vendor và bản build

Tìm trang release notes chính thức của nhà cung cấp JDK. Xác nhận tiêu đề, phiên bản, số build, ngày phát hành và nền tảng được hỗ trợ. Nếu hệ thống dùng image container, kiểm tra cả release notes của image hoặc base distribution khi nhà cung cấp có công bố.

Không trộn lẫn tài liệu của một vendor với runtime của vendor khác mà không ghi nhận sự khác biệt. OpenJDK là nền tảng mã nguồn mở chung, nhưng vendor có thể đóng gói, vá lỗi hoặc hỗ trợ nền tảng theo lịch riêng.

### 3.2. Ưu tiên các mục có thể phá vỡ ứng dụng

Khi đọc, tìm các tiêu đề hoặc từ khóa tương đương sau:

| Mục trong release notes | Điều cần tìm | Tác động có thể gặp |
|---|---|---|
| Removed Features / Removed APIs | Thành phần đã bị loại bỏ | Lỗi compile, `ClassNotFoundException`, `NoClassDefFoundError`. |
| Deprecated Features / APIs | Thành phần bị khuyến cáo ngừng dùng, đặc biệt mục có kế hoạch loại bỏ | Nợ migration và nguy cơ lỗi ở phiên bản sau. |
| Changes / Compatibility | Hành vi hoặc hợp đồng đã thay đổi | Kết quả nghiệp vụ hoặc cách tích hợp khác trước. |
| Security Changes | Thuật toán, giao thức, chứng chỉ hoặc mặc định bảo mật | `SSLHandshakeException`, lỗi xác thực hoặc kết nối bị từ chối. |
| Tools and Utilities | Compiler, công cụ JDK, launcher, monitoring hoặc diagnostic thay đổi | Pipeline build, script hoặc quy trình vận hành bị ảnh hưởng. |
| VM / Runtime Changes | JVM, GC, class loading, memory hoặc tùy chọn runtime | Không khởi động, thay đổi bộ nhớ hoặc độ trễ. |
| Known Issues | Lỗi đã biết và điều kiện tái hiện | Một tính năng hoặc nền tảng cụ thể không hoạt động như mong đợi. |
| Bug Fixes | Lỗi được sửa và hành vi trước/sau khi sửa | Ứng dụng có thể đang phụ thuộc vào hành vi cũ, dù hành vi đó là lỗi. |

Tên mục thay đổi tùy nhà cung cấp. Nếu không có tiêu đề giống hệt, hãy dùng mục lục hoặc tìm kiếm trong trang theo từ khóa liên quan.

### 3.3. Phân biệt tính năng mới, thay đổi mặc định và hành vi bị loại bỏ

Không phải mọi mục mới đều có cùng mức độ rủi ro. Hãy phân loại mỗi thay đổi:

- **Tính năng mới:** thường không ảnh hưởng nếu ứng dụng không sử dụng. Tuy nhiên, cần kiểm tra nếu tính năng thay đổi mặc định hoặc được framework tự động kích hoạt.
- **Thay đổi mặc định:** có thể ảnh hưởng ngay cả khi mã nguồn không đổi, vì ứng dụng vốn dựa vào giá trị mặc định cũ.
- **Deprecated:** API hoặc tính năng vẫn có thể hoạt động nhưng không còn được khuyến nghị. Cần xem mức độ, cảnh báo và mốc loại bỏ dự kiến.
- **Removed:** thành phần không còn tồn tại; mã nguồn hoặc binary phụ thuộc vào nó cần được sửa hoặc thay thế.
- **Bug fix:** có thể làm kết quả khác trước nếu ứng dụng vô tình phụ thuộc vào lỗi đã được sửa.
- **Known issue:** cần xác định điều kiện xuất hiện và biện pháp khắc phục hoặc bản cập nhật đã sửa lỗi.

Đặc biệt, đừng hiểu “deprecated” đồng nghĩa với “đã bị loại bỏ”. Cũng không nên hiểu “bug fix” luôn không gây thay đổi hành vi. Nếu ứng dụng dựa vào hành vi cũ, việc sửa lỗi có thể làm lộ giả định không chính xác trong ứng dụng.

### 3.4. Theo dấu các mục có liên quan đến môi trường ứng dụng

Khi đọc từng mục, đối chiếu với cấu hình và cách ứng dụng đang chạy:

- Nếu release notes nói về TLS hoặc thuật toán mật mã, kiểm tra các endpoint, truststore và chứng chỉ mà ứng dụng sử dụng.
- Nếu nói về JVM options, tìm các cờ trong Dockerfile, script, manifest triển khai và cấu hình service.
- Nếu nói về charset, locale hoặc timezone, tìm các điểm đọc/ghi file, parse ngày giờ và format dữ liệu.
- Nếu nói về module hoặc API, kiểm tra dependency trực tiếp và bắc cầu, reflection và class loading.
- Nếu nói về GC hoặc memory, kiểm tra cấu hình heap, giới hạn container và chỉ số độ trễ.
- Nếu nói về công cụ, kiểm tra pipeline CI, plugin Gradle/Maven, công cụ kiểm thử và agent.

Một mục trong release notes chỉ trở thành rủi ro cụ thể khi có đường phụ thuộc từ ứng dụng đến phần thay đổi đó. Ghi lại đường phụ thuộc và cách xác minh sẽ hữu ích hơn việc chỉ đánh dấu một từ khóa là “có liên quan”.

## 4. Cách sử dụng migration guide

Migration guide thường dài và được chia theo phiên bản hoặc chủ đề. Cách đọc hiệu quả là bắt đầu từ đường nâng cấp, sau đó tìm các nhóm thay đổi tương ứng với kiến trúc và dependency của ứng dụng.

### 4.1. Đọc phần tổng quan và điều kiện tiên quyết

Trước tiên, kiểm tra tài liệu có áp dụng cho phiên bản nguồn, phiên bản đích và vendor đang dùng không. Đọc các điều kiện tiên quyết như phiên bản hệ điều hành được hỗ trợ, kiến trúc CPU, công cụ build và yêu cầu JDK tối thiểu của framework.

Nếu tài liệu hướng dẫn nâng từ phiên bản liền trước nhưng hệ thống đi từ một phiên bản rất cũ, hãy đọc bổ sung các hướng dẫn của những phiên bản nằm giữa. Không được giả định hướng dẫn ngắn từ phiên bản A sang B đã bao phủ mọi thay đổi từ A-5 sang B.

### 4.2. Tìm các chủ đề có xác suất ảnh hưởng cao

Với một ứng dụng Java đang hoạt động, các nhóm dưới đây thường đáng ưu tiên:

1. **API và module:** package, class, method bị loại bỏ hoặc chuyển ra khỏi JDK; module cần được khai báo rõ.
2. **Reflection và encapsulation:** truy cập sâu vào class nội bộ, `--add-opens`, `--add-exports` và cảnh báo truy cập bất hợp pháp.
3. **Compiler và bytecode:** mức source/target, `--release`, phiên bản class file, annotation processor và thư viện xử lý bytecode.
4. **JVM và công cụ:** tùy chọn đã bị loại bỏ, thay đổi GC, unified logging, diagnostic command và monitoring.
5. **Bảo mật và mạng:** TLS, cipher suite, provider, truststore, chứng chỉ và thuật toán đã bị vô hiệu hóa.
6. **Dữ liệu và mặc định:** charset, locale, timezone, định dạng ngày giờ, serialization và encoding.
7. **Framework và dependency:** phiên bản Spring, ORM, driver JDBC, HTTP client, logging, agent, plugin và thư viện native.

Không phải ứng dụng nào cũng bị ảnh hưởng bởi tất cả nhóm. Dùng dependency inventory, cấu hình và luồng nghiệp vụ để xác định chủ đề cần đọc sâu.

### 4.3. Đọc mỗi thay đổi theo cùng một bộ câu hỏi

Với mỗi mục có khả năng liên quan, hãy ghi nhận:

- **What changed:** chính xác điều gì thay đổi?
- **Since when:** thay đổi xuất hiện từ phiên bản nào và có tiếp tục thay đổi ở phiên bản sau không?
- **Who is affected:** API, module, công cụ, hệ điều hành hay kiểu ứng dụng nào chịu tác động?
- **Default or opt-in:** thay đổi tự động áp dụng hay chỉ khi bật một tính năng/cấu hình?
- **Failure mode:** ứng dụng sẽ lỗi khi compile, khi khởi động, khi liên kết hay chỉ khi xử lý một luồng cụ thể?
- **Migration action:** cần sửa mã nguồn, nâng dependency, đổi JVM option, cập nhật cấu hình hay chỉ bổ sung kiểm thử?
- **Evidence:** kiểm tra bằng lệnh, test, log hoặc môi trường nào?

Ví dụ, một mục nói rằng một API đã bị loại bỏ cần được theo dõi thành hai câu hỏi: mã nguồn có import API đó không, và binary đã phát hành có tham chiếu đến class đó không? Nếu chỉ kiểm tra compile một module nhưng còn plugin cũ được nạp ở runtime, vẫn có thể bỏ sót lỗi.

### 4.4. Không sao chép hướng dẫn như một giải pháp tự động

Migration guide có thể đề xuất tùy chọn tạm thời như mở một package module hoặc bật lại một thuật toán. Cần đọc điều kiện và phạm vi của hướng dẫn trước khi áp dụng.

Ví dụ, thêm `--add-opens` có thể giúp thư viện cũ tiếp tục truy cập một trường private trong ngắn hạn. Tuy nhiên, nó không thay thế việc nâng cấp thư viện hoặc chuyển sang API công khai. Tương tự, bật lại thuật toán TLS cũ có thể khôi phục kết nối nhưng làm giảm mức bảo mật.

Mỗi biện pháp cần có lý do, phạm vi áp dụng, người chịu trách nhiệm và điều kiện loại bỏ nếu đó chỉ là giải pháp chuyển tiếp.

## 5. Cách đọc và đánh giá JEP liên quan

JEP giúp hiểu sâu các thay đổi lớn của OpenJDK. Tuy nhiên, danh sách JEP rất dài; không cần đọc mọi JEP của một phiên bản. Hãy tìm những JEP liên quan trực tiếp đến API, runtime, bảo mật, công cụ hoặc giả định mà ứng dụng đang sử dụng.

### 5.1. Xác định JEP và trạng thái của nó

Mỗi JEP có mã số và trang mô tả riêng, ví dụ `JEP 400`. Khi mở một JEP, trước hết hãy kiểm tra:

- Tiêu đề và mã số JEP.
- Người phụ trách (Owner) và người tham gia (Contributors), nếu có.
- Trạng thái hiện tại (Status).
- Phiên bản JDK dự kiến hoặc phiên bản được nhắm đến (Target Release).
- Liên kết đến issue, bản đặc tả, bản triển khai hoặc tài liệu liên quan.

Trạng thái rất quan trọng. Một đề xuất ở giai đoạn Draft hoặc Candidate chưa thể được xem là tính năng chắc chắn có trong JDK mục tiêu. JEP được nhắm đến một bản phát hành vẫn cần theo dõi tiến độ; JEP đã tích hợp cũng cần đối chiếu release notes và bản build thực tế để hiểu chính xác nội dung đã phát hành.

Một JEP có thể được sửa đổi trong quá trình phát triển. Vì vậy, hãy ghi nhận phiên bản tài liệu và trạng thái tại thời điểm nghiên cứu, nhất là khi kế hoạch nâng cấp kéo dài qua nhiều tháng.

### 5.2. Đọc theo cấu trúc của JEP

Một JEP thường có các phần quan trọng sau:

| Phần | Cách đọc | Giá trị đối với migration |
|---|---|---|
| Summary | Đọc để nắm thay đổi trong một vài câu | Xác định JEP có liên quan đến ứng dụng không. |
| Motivation | Tìm vấn đề mà JEP muốn giải quyết | Hiểu lý do thay đổi và vấn đề cũ có thể đang tồn tại trong ứng dụng. |
| Goals | Xác định mục tiêu chính | Biết điều gì được bảo đảm trong phạm vi thiết kế. |
| Non-Goals | Đọc kỹ những điều không được giải quyết | Tránh kỳ vọng tính năng mới xử lý cả các trường hợp ngoài phạm vi. |
| Description | Đọc luồng hoạt động, API và cấu trúc mới | Xác định điểm tích hợp hoặc giả định bị thay đổi. |
| Alternatives | Xem các phương án đã được cân nhắc | Hiểu trade-off và lý do lựa chọn thiết kế. |
| Risks and Assumptions | Tìm rủi ro, giới hạn và giả định | Chuyển rủi ro thành mục kiểm thử cụ thể. |
| Compatibility | Xem tác động với mã nguồn, binary và hành vi | Nhận diện điểm có thể phá vỡ ứng dụng cũ. |
| Testing | Tìm cách tính năng được xác minh | Tham khảo loại bằng chứng cần thu thập trong hệ thống của mình. |

Không phải JEP nào cũng có đủ mọi tiêu đề hoặc cùng một bố cục. Nếu thiếu một mục, hãy tìm thông tin tương ứng trong phần mô tả, liên kết issue hoặc tài liệu triển khai.

### 5.3. Phân biệt JEP với tính năng đã được phát hành

JEP mô tả một cải tiến trong quy trình phát triển OpenJDK; bản thân một JEP không phải lời bảo đảm rằng mọi bản JDK trên thị trường đều có cùng cách đóng gói hoặc cùng trạng thái hỗ trợ.

Khi đọc JEP, cần phân biệt:

- JEP đang đề xuất hoặc thảo luận.
- JEP đã được nhắm đến một bản phát hành.
- JEP đã tích hợp vào mã nguồn của một bản phát triển.
- Tính năng thực tế có trong bản JDK mà ứng dụng sẽ dùng.
- Tính năng đã hoàn tất hay còn ở dạng preview/incubator.

Với tính năng preview hoặc incubator, hãy kiểm tra cờ kích hoạt, điều kiện compile/runtime và khả năng thay đổi ở phiên bản tiếp theo. Không nên sử dụng một tính năng thử nghiệm như hợp đồng ổn định nếu sản phẩm chưa chấp nhận rủi ro đó.

### 5.4. Một số JEP minh họa thường đáng xem khi migration

Các ví dụ sau cho thấy cách nối JEP với câu hỏi thực tế của ứng dụng. Đây không phải danh sách đầy đủ; cần chọn JEP theo đường nâng cấp và dependency cụ thể.

**JEP 403 – Strongly Encapsulate JDK Internals (JDK 17).** JEP này tăng cường đóng gói các API nội bộ của JDK. Nếu framework, thư viện hoặc mã ứng dụng dùng reflection để truy cập sâu vào các package nội bộ, cần kiểm tra cảnh báo và lỗi truy cập. Hướng xử lý dài hạn là chuyển sang API công khai hoặc nâng thư viện; tùy chọn mở module chỉ nên là biện pháp có phạm vi rõ ràng.

**JEP 400 – UTF-8 by Default (JDK 18).** JEP này chuẩn hóa UTF-8 làm charset mặc định trong các môi trường tiêu chuẩn. Nếu ứng dụng đọc hoặc ghi dữ liệu bằng charset mặc định, hãy kiểm tra định dạng file, giao thức và dữ liệu được tạo bởi hệ thống cũ. Cách bền vững là chỉ định encoding theo hợp đồng dữ liệu.

**JEP 444 – Virtual Threads (JDK 21).** JEP này đưa virtual threads thành tính năng chính thức. Nếu ứng dụng chọn áp dụng virtual threads, cần đánh giá mô hình đồng thời, giới hạn tài nguyên, thư viện dùng thread-local hoặc native call và đặc tính tải. Chỉ nâng JDK lên 21 không có nghĩa ứng dụng tự động chuyển sang virtual threads; đây là lựa chọn thiết kế cần được kiểm thử riêng.

**JEP 451 – Prepare to Disallow the Dynamic Loading of Agents (JDK 21).** JEP này chuẩn bị hạn chế việc nạp Java agent động trong tương lai và đưa ra cảnh báo trong một số trường hợp ở JDK 21. Nếu công cụ APM, profiler, test hoặc framework gắn agent sau khi JVM đã chạy, cần xác định cách nạp agent và kiểm tra cảnh báo. Cách nạp agent lúc khởi động và cơ chế cho phép attach có thể có yêu cầu vận hành khác nhau.

Khi sử dụng các ví dụ này, hãy mở trang JEP để đọc mục tiêu, phạm vi và trạng thái hiện tại; sau đó kiểm tra release notes của đúng bản JDK. Tên JEP và mô tả ngắn không thay thế việc xác nhận cấu hình runtime thực tế.

## 6. Kết nối ba nguồn tài liệu thành một quy trình nghiên cứu

Đọc riêng lẻ từng nguồn thường tạo ra nhiều ghi chú nhưng khó biến thành quyết định kỹ thuật. Nên kết nối chúng thành một chuỗi: xác định thay đổi trong release notes, hiểu tác động và phương án trong migration guide, rồi đọc JEP khi cần giải thích thiết kế hoặc rủi ro sâu hơn.

```text
Xác định JDK nguồn và JDK đích
              |
              v
Release notes của đúng vendor/build
              |
              v
Đánh dấu thay đổi, lỗi đã biết, bảo mật,
API, JVM options và hành vi mặc định
              |
              v
Migration guide theo đường nâng cấp
              |
              v
Xác định ứng dụng/dependency nào bị ảnh hưởng
              |
              v
JEP liên quan để hiểu thiết kế, phạm vi,
trạng thái và rủi ro tương thích
              |
              v
Lập biện pháp, bằng chứng và kiểm thử
              |
              v
Thử nghiệm trên môi trường mục tiêu
```

### Bước 1: Tạo danh sách nguồn theo đường nâng cấp

Ví dụ, khi chuyển từ Java 11 lên Java 21, tạo danh sách release notes và migration guide cho các mốc phiên bản liên quan, cùng các tài liệu của vendor đang sử dụng. Với từng mốc, ghi lại số phiên bản và đường dẫn chính thức.

Không cần đọc mọi mục với cùng độ sâu. Hãy bắt đầu bằng mục lục và từ khóa, sau đó đọc toàn văn các mục có liên hệ đến dependency, cấu hình hoặc luồng nghiệp vụ đang tồn tại.

### Bước 2: Tạo bảng thay đổi và tác động

Mỗi thay đổi tìm được nên được ghi thành một dòng có thể theo dõi:

| Trường | Nội dung cần ghi |
|---|---|
| Version | Phiên bản hoặc bản cập nhật đưa thay đổi vào. |
| Source | Release notes, migration guide hay JEP; kèm liên kết và mục/đoạn liên quan. |
| Change | Mô tả ngắn gọn điều thay đổi. |
| Affected area | Module, API, framework, JVM option, bảo mật, dữ liệu hoặc môi trường. |
| Application usage | Bằng chứng ứng dụng đang sử dụng phần bị ảnh hưởng. |
| Risk | Có thể lỗi compile, link, runtime, dữ liệu, bảo mật hay hiệu năng. |
| Action | Sửa mã, nâng dependency, thay cấu hình, cập nhật image hoặc bổ sung test. |
| Verification | Lệnh, test, log hoặc metric dùng để xác nhận. |
| Status | Chưa điều tra, đã xác nhận không ảnh hưởng, cần sửa, đã sửa hoặc đã kiểm chứng. |

Ví dụ về cách ghi một mục:

| Trường | Ví dụ minh họa |
|---|---|
| Version | JDK 18 |
| Source | JEP 400 và migration guide tương ứng |
| Change | UTF-8 trở thành charset mặc định trong môi trường tiêu chuẩn. |
| Affected area | Đọc/ghi file CSV và import dữ liệu từ hệ thống cũ. |
| Application usage | Một đoạn code gọi `new String(bytes)` mà không truyền charset. |
| Risk | Ký tự có dấu có thể được giải mã khác với dữ liệu nguồn. |
| Action | Xác định encoding của file và chỉ định charset tường minh. |
| Verification | Test file mẫu có ký tự tiếng Việt bằng JDK cũ và mới. |
| Status | Đã xác định cần sửa; chờ kiểm thử. |

Đây là ví dụ về phương pháp ghi nhận, không phải kết luận rằng mọi ứng dụng đều gặp lỗi khi nâng lên JDK 18. Chỉ đánh dấu ảnh hưởng khi đã tìm thấy đường phụ thuộc trong chính ứng dụng.

### Bước 3: Liên kết thay đổi với code và dependency

Tìm các package, class, method, JVM options hoặc cấu hình được nhắc trong tài liệu. Đối chiếu với source code, dependency tree, Dockerfile, pipeline và lệnh khởi động.

Một thay đổi chỉ được xem là có liên quan khi có bằng chứng như:

- Mã nguồn import hoặc gọi API bị thay đổi.
- Dependency trực tiếp hoặc bắc cầu sử dụng API đó.
- Framework dùng reflection hoặc truy cập nội bộ.
- Script triển khai truyền JVM option bị ảnh hưởng.
- Luồng nghiệp vụ kết nối đến endpoint hoặc xử lý dữ liệu chịu thay đổi.
- Công cụ quan sát hoặc agent dựa vào cơ chế runtime bị thay đổi.

Nếu chưa tìm thấy bằng chứng, ghi rõ “chưa xác định” thay vì kết luận “không ảnh hưởng”. Có thể cần kiểm tra runtime, plugin hoặc cấu hình được nạp động mà tìm kiếm source code không phát hiện được.

### Bước 4: Đọc sâu JEP khi thay đổi có tác động rộng

Nếu release notes hoặc migration guide nhắc đến một JEP, mở JEP để hiểu rõ thiết kế. Nếu không có liên kết trực tiếp, có thể tìm JEP theo chủ đề hoặc mã số tính năng trong OpenJDK.

Đọc phần Compatibility, Risks, Non-Goals và các liên kết triển khai để xác định điều gì thực sự thay đổi. Ghi lại trạng thái và target release để tránh đưa một đề xuất chưa được phát hành vào kế hoạch như thể đó là hành vi hiện tại.

### Bước 5: Chuyển ghi chú thành kế hoạch kiểm thử

Mỗi rủi ro phải dẫn đến ít nhất một cách xác minh. Ví dụ:

| Phát hiện từ tài liệu | Kiểm tra cần thực hiện |
|---|---|
| API bị loại bỏ | Compile toàn bộ consumer; chạy artifact cũ nếu còn binary triển khai độc lập. |
| Truy cập nội bộ bị đóng gói | Chạy integration test với JDK mục tiêu và kiểm tra cảnh báo reflection. |
| JVM option thay đổi | Khởi động ứng dụng bằng đúng command line production. |
| Chính sách TLS thay đổi | Kiểm tra handshake với các endpoint thực tế và truststore mục tiêu. |
| Charset mặc định thay đổi | Đọc/ghi bộ file mẫu có encoding được quy định. |
| Thay đổi GC hoặc memory | Chạy tải đại diện và so sánh heap, pause, p95/p99. |
| JEP đưa tính năng mới | Chỉ kiểm thử nếu ứng dụng chủ động sử dụng hoặc cấu hình bật tính năng đó. |

Sau khi test đạt, cập nhật trạng thái trong bảng thay đổi cùng log, kết quả test hoặc số liệu có thể truy xuất. Không đánh dấu hoàn tất chỉ vì đã đọc tài liệu hoặc đã sửa code.

## 7. Những lỗi thường gặp khi đọc tài liệu nâng cấp

### Chỉ đọc release notes của phiên bản đích

Nếu ứng dụng nâng qua nhiều phiên bản lớn, thay đổi có thể đã xuất hiện từ phiên bản trung gian. Chỉ đọc trang phiên bản đích dễ bỏ qua một thay đổi cũ nhưng vẫn ảnh hưởng đường nâng cấp hiện tại.

### Dùng tài liệu của vendor khác

Một hướng dẫn của Oracle JDK có thể hữu ích để hiểu thay đổi chung của nền tảng, nhưng không nhất thiết mô tả đầy đủ cách đóng gói, bản vá, hỗ trợ nền tảng hoặc lỗi riêng của Temurin, Corretto hay bản phân phối khác. Cần dùng tài liệu vendor thực tế làm nguồn xác nhận triển khai.

### Xem JEP như cam kết tính năng đã có

Một JEP đang Draft, Candidate hoặc chưa tích hợp không chứng minh tính năng đã có trong bản JDK đang dùng. Luôn kiểm tra status, target release, release notes và trạng thái preview/incubator.

### Chỉ đọc tính năng mới mà bỏ qua phần bị loại bỏ

Đối với migration, các mục Removed, Deprecated, Security, Compatibility và Known Issues thường có giá trị trực tiếp hơn danh sách tính năng mới. Đặc biệt cần tìm các thay đổi mặc định và các tùy chọn JVM đã bị loại bỏ.

### Ghi chú thay đổi nhưng không tìm đường phụ thuộc

Một JEP có thể rất quan trọng với hệ sinh thái nhưng không liên quan đến ứng dụng cụ thể. Ngược lại, một thay đổi nhỏ trong TLS hoặc charset có thể ảnh hưởng trực tiếp đến một luồng nghiệp vụ quan trọng. Hãy dựa vào code, dependency, cấu hình và kiểm thử để xác định mức độ ảnh hưởng.

### Coi migration guide là danh sách thao tác phải áp dụng hết

Hướng dẫn có thể nêu nhiều cách xử lý cho các tình huống khác nhau. Không nên thêm mọi JVM option hoặc dependency được đề cập vào ứng dụng. Chọn giải pháp dựa trên nguyên nhân đã xác nhận, phạm vi cần thiết và yêu cầu bảo mật/vận hành.

## 8. Nguồn tài liệu chính thức nên bắt đầu từ đâu?

Ưu tiên nguồn do dự án OpenJDK hoặc vendor của JDK đang chạy công bố. Một số điểm bắt đầu hữu ích:

- **OpenJDK JEP Index:** [https://openjdk.org/jeps/0](https://openjdk.org/jeps/0) — tra cứu JEP, mã số, trạng thái và liên kết đến tài liệu từng cải tiến.
- **Oracle Java SE 21 Documentation:** [https://docs.oracle.com/en/java/javase/21/](https://docs.oracle.com/en/java/javase/21/) — từ đây có thể mở Migration Guide, công cụ, đặc tả và tài liệu runtime cho Java 21.
- **Oracle Java SE 21 Release Notes:** [https://www.oracle.com/java/technologies/javase/21all-relnotes.html](https://www.oracle.com/java/technologies/javase/21all-relnotes.html) — ghi chú phát hành theo bản cập nhật của Oracle JDK 21.
- **OpenJDK JDK Project Pages:** [https://openjdk.org/projects/](https://openjdk.org/projects/) — theo dõi các dự án, phiên bản và thông tin phát triển OpenJDK.

Nếu production sử dụng một bản phân phối khác, hãy tìm trang release notes, security advisories, support matrix và migration documentation chính thức của vendor đó. Các đường dẫn trên là điểm bắt đầu minh họa cho Java 21; khi nâng lên phiên bản khác, hãy thay bằng tài liệu đúng phiên bản mục tiêu.

## 9. Checklist nghiên cứu trước khi nâng cấp

Trước khi kết luận đã nghiên cứu đủ tài liệu, có thể đối chiếu các câu hỏi sau:

- [ ] Đã ghi nhận chính xác JDK nguồn và JDK đích, vendor, build và môi trường chạy.
- [ ] Đã xác định các phiên bản trung gian cần rà soát.
- [ ] Đã đọc release notes của đúng vendor và bản cập nhật mục tiêu.
- [ ] Đã tìm các mục Removed, Deprecated, Compatibility, Security, JVM, Tools và Known Issues.
- [ ] Đã đọc migration guide theo đường nâng cấp, không chỉ hướng dẫn của phiên bản liền trước.
- [ ] Đã tìm JEP liên quan và xác nhận status, target release, preview/incubator nếu có.
- [ ] Đã phân loại thay đổi thành tính năng mới, thay đổi mặc định, deprecated, removed, bug fix hoặc known issue.
- [ ] Đã nối từng thay đổi có liên quan với source code, dependency, cấu hình hoặc luồng nghiệp vụ cụ thể.
- [ ] Đã ghi rõ hành động migration và bằng chứng kiểm thử cần có.
- [ ] Đã lưu đường dẫn nguồn và phiên bản tài liệu để người khác có thể kiểm tra lại.

Checklist này giúp tổ chức việc nghiên cứu; nó không thay thế việc kiểm thử. Một mục được đánh dấu chỉ khi có bằng chứng phù hợp, chẳng hạn link tài liệu, dependency tree, kết quả compile, integration test hoặc số liệu runtime.

## 10. Kết luận

Release notes, migration guide và JEP cung cấp ba góc nhìn bổ sung cho quá trình nâng cấp JDK. Release notes xác nhận nội dung của bản phát hành cụ thể; migration guide giải thích tác động và cách chuyển đổi; JEP làm rõ mục tiêu, thiết kế, phạm vi và rủi ro của một cải tiến trong OpenJDK.

Quy trình hiệu quả bắt đầu bằng việc xác định đúng JDK nguồn, JDK đích, vendor và build. Sau đó, đọc release notes theo từng mốc phiên bản, dùng migration guide để tìm các điểm có thể phá vỡ ứng dụng, rồi mở JEP liên quan để hiểu sâu những thay đổi quan trọng. Cuối cùng, liên kết từng phát hiện với code, dependency và cấu hình thật, chuyển chúng thành kiểm thử có thể lặp lại và lưu bằng chứng.

Đọc tài liệu chỉ giúp phát hiện rủi ro tiềm ẩn. Chỉ khi đã xác định được ứng dụng có sử dụng phần bị thay đổi hay không và đã kiểm tra trên môi trường mục tiêu, nhóm mới có cơ sở quyết định cách nâng cấp và mức độ sẵn sàng triển khai.
