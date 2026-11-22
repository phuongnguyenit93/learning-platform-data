# Từ kiểm kê hiện trạng đến kiểm chứng và phát hành

Di chuyển phiên bản Java là một thay đổi có ảnh hưởng xuyên suốt từ mã nguồn, thư viện, công cụ build đến môi trường chạy và quy trình vận hành. Một dự án biên dịch thành công trên máy lập trình viên chưa đủ chứng minh dự án tương thích với nền tảng đích. Ứng dụng còn phải khởi động được, giữ đúng hành vi nghiệp vụ, kết nối được với các hệ thống phụ thuộc, đáp ứng yêu cầu hiệu năng và có phương án phát hành an toàn.

Vì vậy, một đợt Java compatibility migration cần đi theo chuỗi có thể kiểm chứng: ghi nhận hiện trạng, xác định đích đến, tìm khoảng cách tương thích, lập kế hoạch xử lý, thay đổi có kiểm soát, kiểm thử trên môi trường đại diện, rồi phát hành kèm bằng chứng và phương án quay lui. Mỗi giai đoạn tạo ra đầu vào rõ ràng cho giai đoạn tiếp theo. Cách làm này giúp nhóm biết chính xác điều gì đã được kiểm tra, điều gì còn chưa chắc chắn và ai chịu trách nhiệm xử lý phần còn thiếu.

## 1. Xác định mục tiêu và phạm vi di chuyển

Trước khi kiểm tra mã nguồn, cần viết rõ mục tiêu của đợt di chuyển. “Nâng cấp Java” có thể chỉ việc đổi JDK chạy ứng dụng, nhưng cũng có thể bao gồm nâng mức ngôn ngữ biên dịch, thay đổi framework, cập nhật thư viện, đổi công cụ build hoặc chuyển image triển khai. Những thay đổi này có quan hệ với nhau nhưng không đồng nhất.

Hãy phân biệt các phiên bản sau:

| Thành phần | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| JDK dùng để chạy build | JDK khởi chạy Gradle, Maven và các plugin build | Công cụ build và plugin có chạy được trên JDK này không? |
| JDK/toolchain biên dịch | JDK mà compiler sử dụng để biên dịch mã nguồn | Mã nguồn được biên dịch bằng compiler và API của phiên bản nào? |
| Mức API đích | Tập API Java mà mã đã biên dịch được phép sử dụng | Artifact có thể chạy trên runtime tối thiểu đã cam kết không? |
| JRE/JDK chạy ứng dụng | JVM thực tế khởi chạy ứng dụng trong máy chủ hoặc container | Runtime có đúng phiên bản, nhà cung cấp và cấu hình đã kiểm chứng không? |
| Phiên bản framework và thư viện | Các thành phần bên ngoài cung cấp chức năng cho ứng dụng | Các phiên bản này có hỗ trợ JDK và framework đích không? |

Một dự án có thể dùng JDK mới để chạy Gradle nhưng vẫn biên dịch bytecode cho một phiên bản Java thấp hơn. Ngược lại, dự án có thể biên dịch thành công nhưng được triển khai trên runtime quá cũ để nạp bytecode hoặc cung cấp API mà ứng dụng đang sử dụng. Vì vậy, tài liệu di chuyển phải ghi riêng từng phiên bản, không gom tất cả thành một trường “Java version”.

Phạm vi cũng cần xác định rõ:

- Những module nào được di chuyển trong đợt này; module dùng chung nào có thể ảnh hưởng đến nhiều ứng dụng.
- Phiên bản JDK, framework, build tool và môi trường triển khai đích.
- Có thay đổi cấu hình, container image, hệ điều hành, driver cơ sở dữ liệu hoặc giao thức tích hợp hay không.
- Những chức năng, API và hệ thống bên ngoài nào bắt buộc giữ nguyên hành vi.
- Tiêu chí hoàn thành, thời điểm phát hành và điều kiện phải dừng hoặc quay lui.

Nếu phạm vi chưa rõ, kết quả kiểm kê sẽ khó phân biệt giữa lỗi thuộc đợt di chuyển và vấn đề đã tồn tại từ trước.

## 2. Kiểm kê hiện trạng trước khi thay đổi

Kiểm kê hiện trạng tạo ra đường cơ sở (baseline) để so sánh trước và sau di chuyển. Hãy thực hiện trên một commit xác định, lưu lại lệnh đã chạy và kết quả quan trọng. Không nên vừa kiểm kê vừa nâng cấp thư viện hoặc sửa cấu hình, vì khi đó nhóm không còn biết trạng thái ban đầu thực sự là gì.

### 2.1. Kiểm kê nền tảng Java và công cụ build

Ghi nhận ít nhất:

- Phiên bản, nhà cung cấp và đường dẫn JDK trên máy lập trình viên, CI và môi trường chạy.
- Giá trị `JAVA_HOME`, `PATH`, cấu hình toolchain và các biến môi trường có ảnh hưởng đến việc chọn JDK.
- Phiên bản Gradle Wrapper hoặc Maven Wrapper; phiên bản plugin build và plugin do dự án tự phát triển.
- Mức source, target hoặc `release` của compiler; encoding; annotation processor; compiler arguments.
- Các tác vụ build, kiểm thử, đóng gói, phân tích mã và tạo tài liệu đang được CI thực hiện.

Với Gradle, các lệnh khảo sát thường dùng gồm:

```bash
./gradlew --version
./gradlew projects
./gradlew tasks
```

Với Maven Wrapper:

```bash
./mvnw -version
./mvnw help:effective-pom
```

Trên Windows có thể dùng `gradlew.bat` hoặc `mvnw.cmd`. Cần lưu ý rằng kết quả `java -version` trong terminal không nhất thiết phản ánh JDK mà CI hoặc Gradle daemon đang sử dụng. Hãy đọc log build và cấu hình toolchain để xác nhận thực tế.

### 2.2. Kiểm kê dependency và quan hệ phụ thuộc

Danh sách dependency trực tiếp chưa thể hiện đầy đủ những gì ứng dụng nạp lúc chạy. Một thư viện có thể kéo theo nhiều dependency bắc cầu; cùng một thư viện cũng có thể xuất hiện ở nhiều phiên bản do các nhánh phụ thuộc khác nhau.

Với Gradle, có thể xem cây dependency và truy nguyên một thư viện cụ thể:

```bash
./gradlew dependencies
./gradlew dependencyInsight --dependency <ten-thu-vien>
```

Với Maven:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=<groupId>:<artifactId>
```

Khi ghi nhận dependency, cần phân biệt:

- Dependency trực tiếp do module khai báo.
- Dependency bắc cầu do thư viện khác kéo vào.
- Dependency chỉ phục vụ biên dịch, kiểm thử hoặc annotation processing.
- Dependency được cung cấp bởi runtime, container hoặc nền tảng triển khai.
- Dependency nội bộ giữa các module và artifact được đóng gói kèm.

Đối với mỗi thư viện quan trọng, ghi phiên bản đang dùng, phiên bản dự kiến, nguồn khai báo, đường đi phụ thuộc, phạm vi sử dụng và thông tin hỗ trợ JDK/framework đích. Không nên chỉ nhìn phiên bản mới nhất trên kho package rồi kết luận rằng đó là phiên bản phù hợp; cần kiểm tra tài liệu tương thích, thay đổi API, yêu cầu runtime và quan hệ với các dependency liên quan.

### 2.3. Kiểm kê framework, API và cấu hình

Lập danh sách framework và thành phần nền tảng như web framework, persistence, dependency injection, logging, JSON, validation, security, messaging, cache, database driver và thư viện kiểm thử. Với từng thành phần, xác định phiên bản, cách cấu hình, điểm tích hợp và module sử dụng.

Đặc biệt chú ý các điểm có thể phụ thuộc vào hành vi của JDK:

- Reflection, proxy, bytecode generation và truy cập thành phần nội bộ của JDK.
- Serialization, định dạng ngày giờ, locale, timezone và charset mặc định.
- TLS, chứng thư, thuật toán mật mã và chính sách bảo mật.
- Class loading, service provider, Java Platform Module System và resource lookup.
- Thread, executor, đồng bộ, timeout, interrupt và xử lý lỗi bất đồng bộ.
- File system, quyền truy cập, encoding đường dẫn và hành vi của hệ điều hành.

Kiểm kê cả cấu hình nằm ngoài mã nguồn: biến môi trường, JVM options, system properties, file cấu hình theo profile, secret reference, container image, tham số khởi động, health check và cấu hình CI/CD. Nhiều lỗi chỉ xuất hiện vì môi trường mới có giá trị mặc định khác môi trường cũ.

### 2.4. Kiểm kê hành vi và bằng chứng hiện có

Không chỉ ghi “có test” hoặc “build đang xanh”. Cần biết test nào thực sự chạy, test nào bị bỏ qua, module nào chưa có kiểm thử và những luồng nghiệp vụ quan trọng nào chưa được bao phủ.

Hãy lập danh sách các luồng cần bảo vệ, chẳng hạn:

- Khởi động ứng dụng, đăng ký bean và nạp cấu hình.
- Xác thực, phân quyền và xử lý request/response.
- Đọc ghi cơ sở dữ liệu, transaction, migration schema và connection pool.
- Gọi dịch vụ ngoài, xử lý timeout, retry và lỗi mạng.
- Gửi nhận message, xử lý tác vụ nền và đóng ứng dụng có trật tự.
- Sinh file, đọc ghi dữ liệu, xử lý ngày giờ và dữ liệu có ký tự ngoài ASCII.
- Các luồng có yêu cầu cao về độ trễ, thông lượng hoặc bộ nhớ.

Lưu lại kết quả build và test, log khởi động, số liệu hiệu năng nếu có, lỗi đã biết và các cảnh báo đang tồn tại. Đường cơ sở này giúp phân biệt regression do di chuyển với lỗi có từ trước.

### 2.5. Tạo bản ghi kiểm kê có thể truy vết

Một bản ghi kiểm kê hữu ích nên có các cột sau:

| Trường | Nội dung |
|---|---|
| Thành phần | Tên module, thư viện, plugin hoặc môi trường |
| Hiện trạng | Phiên bản và cấu hình đang dùng |
| Đích đến | Phiên bản/cấu hình dự kiến |
| Nguồn bằng chứng | File cấu hình, lệnh, log, tài liệu hoặc người xác nhận |
| Phạm vi ảnh hưởng | Module, luồng nghiệp vụ và môi trường liên quan |
| Mức chắc chắn | Đã xác nhận, mới suy luận hoặc chưa có dữ liệu |
| Người phụ trách | Người theo dõi và xử lý vấn đề |

Ghi cả những điểm chưa biết. Một ô “chưa xác định” có chủ sở hữu và thời hạn xử lý sẽ an toàn hơn một giá trị được đoán rồi bị coi như sự thật.

## 3. Xác định ma trận tương thích đích

Sau khi có baseline, xây dựng ma trận tương thích cho toàn bộ tổ hợp sẽ được phát hành. Không kiểm tra từng thành phần một cách cô lập nếu chúng chỉ hoạt động trong một tổ hợp cụ thể.

Ví dụ, JDK đích có thể được hỗ trợ bởi phiên bản framework mới, nhưng plugin build hiện tại lại không chạy được trên JDK đó. Một driver cơ sở dữ liệu có thể hỗ trợ JDK mới nhưng phiên bản đang dùng của framework không tương thích với phiên bản driver mới. Ma trận phải thể hiện được các quan hệ này.

| Nhóm | Hiện trạng | Đích đến | Điều kiện cần xác minh |
|---|---|---|---|
| JDK/runtime | Phiên bản và vendor hiện tại | JDK/runtime dự kiến | Hỗ trợ chính thức, JVM options, image triển khai |
| Compiler/toolchain | Compiler và mức API hiện tại | Compiler/toolchain đích | Source compatibility, bytecode, API được phép dùng |
| Build tool/plugin | Wrapper và plugin hiện tại | Phiên bản tương thích | Khả năng chạy trên JDK dùng để build |
| Framework | Phiên bản đang dùng | Phiên bản mục tiêu | Ma trận hỗ trợ JDK, API thay đổi, cấu hình |
| Dependency | Trực tiếp và bắc cầu | Phiên bản được chốt | Tương thích lẫn nhau, license, bảo mật |
| Runtime platform | OS, container, server | Môi trường phát hành | Image, chứng thư, timezone, quyền và tài nguyên |
| Hệ thống tích hợp | Database, broker, API ngoài | Phiên bản/cấu hình thực tế | Driver, giao thức, TLS, schema và contract |

Với mỗi ô hoặc quan hệ trong ma trận, dùng trạng thái rõ ràng:

- **Đã xác nhận hỗ trợ:** có tài liệu chính thức hoặc cam kết hỗ trợ phù hợp với tổ hợp đang xét.
- **Đã kiểm chứng:** nhóm đã chạy thử trên đúng tổ hợp và lưu bằng chứng.
- **Chưa xác định:** thiếu tài liệu hoặc chưa có môi trường kiểm tra.
- **Không tương thích:** có bằng chứng cho thấy tổ hợp không hoạt động hoặc nằm ngoài hỗ trợ.
- **Có điều kiện/biện pháp thay thế:** chỉ dùng được khi áp dụng cấu hình, phiên bản hoặc workaround đã ghi rõ.

“Được nhà cung cấp hỗ trợ” và “đã được dự án kiểm chứng” là hai kết luận khác nhau. Ma trận tốt phải thể hiện cả hai, tránh dùng một kết luận chung để che khuất phần chưa thử nghiệm.

## 4. Phân tích khoảng cách và xếp thứ tự rủi ro

So sánh baseline với ma trận đích để lập danh sách khoảng cách (compatibility gaps). Mỗi khoảng cách nên mô tả hiện tượng, điều kiện tái hiện, phạm vi ảnh hưởng, bằng chứng, mức độ nghiêm trọng, hướng xử lý và tiêu chí đóng.

Những nhóm rủi ro thường gặp gồm:

1. **API bị loại bỏ hoặc thay đổi:** mã nguồn gọi API không còn tồn tại, API đổi chữ ký hoặc thay đổi hợp đồng.
2. **Truy cập API nội bộ:** thư viện hoặc ứng dụng phụ thuộc vào package nội bộ của JDK; cơ chế đóng gói module và kiểm soát truy cập ở runtime mới có thể chặn hành vi này.
3. **Không tương thích nhị phân:** mã đã biên dịch tham chiếu class, method hoặc field không còn được cung cấp ở runtime thực tế.
4. **Dependency lỗi thời:** thư viện, plugin hoặc annotation processor không hỗ trợ JDK đích; dependency bắc cầu xung đột hoặc kéo phiên bản không phù hợp.
5. **Thay đổi mặc định runtime:** charset, timezone, TLS, thuật toán bảo mật, GC, reflection hoặc cách xử lý warning thay đổi.
6. **Khác biệt framework:** lifecycle, auto-configuration, mapping request, transaction, serialization hoặc cơ chế proxy thay đổi.
7. **Khác biệt môi trường:** container thiếu công cụ hoặc chứng thư, giới hạn bộ nhớ khác, quyền file khác hoặc biến môi trường chưa được cập nhật.
8. **Thiếu bằng chứng:** luồng quan trọng không có test, môi trường tích hợp không sẵn sàng hoặc không có số liệu để đánh giá regression.

Có thể dùng ba mức ưu tiên để điều phối công việc:

| Mức | Dấu hiệu | Cách xử lý |
|---|---|---|
| Chặn phát hành | Build không hoàn tất, ứng dụng không khởi động, luồng cốt lõi sai, dữ liệu có nguy cơ hỏng hoặc không có phương án phục hồi | Phải xử lý hoặc có quyết định ngoại lệ được phê duyệt trước khi phát hành |
| Cao | Ảnh hưởng luồng quan trọng, bảo mật, độ ổn định hoặc hiệu năng; có khả năng xuất hiện ở production | Ưu tiên xử lý và kiểm chứng trên môi trường đại diện |
| Trung bình/thấp | Phạm vi hẹp, có cách phát hiện và kiểm soát, không làm sai tiêu chí phát hành | Lên lịch xử lý, ghi rõ chủ sở hữu và điều kiện chấp nhận |

Không nên xếp hạng chỉ dựa trên số lượng lỗi. Một lỗi hiếm nhưng có thể làm sai dữ liệu hoặc vô hiệu hóa xác thực có mức rủi ro cao hơn nhiều lỗi cảnh báo không ảnh hưởng hành vi. Cần xem xét đồng thời xác suất xảy ra, mức độ thiệt hại, khả năng phát hiện và khả năng phục hồi.

Với mỗi vấn đề, tạo một mục theo dõi có cấu trúc:

```text
ID: COMPAT-001
Thành phần: thư viện X
Hiện tượng: truy cập API không còn được phép trên runtime đích
Điều kiện: khởi động module Y với cấu hình Z
Ảnh hưởng: module Y không thể khởi động
Bằng chứng: log lỗi và kết quả kiểm tra dependency
Ưu tiên: chặn phát hành
Hướng xử lý: nâng thư viện hoặc thay thế cách tích hợp
Chủ sở hữu: người phụ trách module Y
Tiêu chí đóng: test khởi động và integration test chạy thành công trên runtime đích
```

Một vấn đề chỉ nên được đóng khi có bằng chứng thỏa tiêu chí đã thống nhất, không phải chỉ vì đã tạo commit hoặc sửa xong theo nhận định của người thực hiện.

## 5. Lập kế hoạch và chuẩn bị đường di chuyển

Kế hoạch di chuyển cần chuyển từng khoảng cách thành công việc có thứ tự, phụ thuộc, người phụ trách và điều kiện hoàn thành. Những thay đổi nền tảng thường có quan hệ trước sau: build tool phải chạy được trên JDK dùng để build; framework phải hỗ trợ JDK đích; dependency liên quan phải có phiên bản tương thích; cuối cùng ứng dụng phải được kiểm chứng trên runtime triển khai.

Trước khi sửa mã:

- Chốt commit baseline và tạo nhánh di chuyển theo quy ước của nhóm.
- Xác nhận build và test trên baseline; lưu các lỗi có sẵn.
- Chốt phiên bản mục tiêu và nguồn tài liệu tương thích.
- Kiểm tra CI có thể cài đặt, chọn và sử dụng đúng JDK/toolchain.
- Chuẩn bị môi trường kiểm thử gần với production về runtime, container, cấu hình và dịch vụ tích hợp.
- Bảo đảm có test cho luồng nghiệp vụ quan trọng; bổ sung test đặc trưng trước khi thay đổi nếu cần.
- Chốt cách quản lý dependency để kết quả build có thể tái lập.
- Xác định người có quyền quyết định khi gặp dependency không còn được hỗ trợ hoặc cần ngoại lệ.

Ưu tiên chia nhỏ thay đổi theo nhóm có thể kiểm chứng độc lập. Chẳng hạn, có thể tách cập nhật wrapper/plugin, cấu hình toolchain, nâng framework, xử lý API bị loại bỏ và thay đổi image triển khai thành các bước riêng. Tuy nhiên, thứ tự cuối cùng phải tuân theo quan hệ tương thích thực tế của dự án; không áp dụng máy móc một thứ tự duy nhất cho mọi hệ thống.

Mỗi bước nên có điều kiện vào và điều kiện ra. Ví dụ, chỉ bắt đầu nâng framework khi đã xác nhận build tool chạy được với JDK dự kiến và đã có danh sách dependency bị framework quản lý. Chỉ chuyển sang kiểm thử tích hợp khi ứng dụng đã biên dịch, đóng gói và khởi động trên runtime đích.

## 6. Thực hiện di chuyển có kiểm soát

### 6.1. Đồng bộ môi trường build và runtime

Đầu tiên, bảo đảm máy lập trình viên, CI và môi trường triển khai không vô tình chọn các JDK khác nhau. Dùng Wrapper và toolchain được khai báo trong dự án để giảm phụ thuộc vào cấu hình máy cá nhân. Log build nên thể hiện JDK thực tế, phiên bản build tool và các tham số compiler quan trọng.

Với `javac`, tùy chọn `--release` giúp ràng buộc cả mức ngôn ngữ, bytecode và tập API nền tảng được phép dùng cho release mục tiêu. Chỉ đặt riêng `source` và `target` có thể chưa đủ để ngăn mã nguồn tham chiếu API chỉ tồn tại ở JDK mới hơn. Với Gradle hoặc Maven, hãy cấu hình cơ chế tương đương theo phiên bản plugin compiler đang sử dụng.

Ví dụ minh họa khi biên dịch trực tiếp:

```bash
javac --release 21 -d build/classes src/example/App.java
```

Số `21` chỉ là ví dụ; phải thay bằng mức Java đã được phê duyệt cho dự án. Nếu mục tiêu là chạy trên JDK đích, hãy xác minh cả compiler lẫn runtime thực tế, không suy ra runtime từ cấu hình compiler.

### 6.2. Nâng build tool và plugin theo ma trận hỗ trợ

Gradle/Maven và plugin là một phần của nền tảng build. Plugin có thể dùng API JDK, thư viện bytecode hoặc cơ chế reflection riêng, nên có thể hỏng dù mã nguồn ứng dụng không thay đổi.

Khi cập nhật:

- Dùng phiên bản Wrapper đã được kiểm tra với JDK chạy build.
- Kiểm tra plugin của Java, Spring, Kotlin, code generation, coverage, static analysis và đóng gói.
- Đọc release notes của phiên bản có thay đổi hành vi hoặc cấu hình.
- Chạy các tác vụ build thực tế của CI, không chỉ một tác vụ compile đơn giản.
- Kiểm tra script build tự viết và plugin nội bộ nếu chúng dùng API đã thay đổi.

Nếu build tool không thể chạy trên JDK đích, cần giải quyết ràng buộc này trong kế hoạch trước khi chuyển các bước tiếp theo.

### 6.3. Cập nhật dependency và framework

Ưu tiên cập nhật theo ma trận phiên bản tương thích và quan hệ quản lý dependency. Nếu framework cung cấp BOM hoặc cơ chế quản lý phiên bản tập trung, cần hiểu rõ phiên bản nào được framework kiểm soát và dependency nào dự án tự ghim. Không nâng ngẫu nhiên từng thư viện lên bản mới nhất vì điều đó có thể tạo ra tổ hợp chưa được hỗ trợ.

Sau mỗi lần cập nhật dependency:

- Kiểm tra cây dependency để phát hiện phiên bản bị thay thế, trùng lặp hoặc xung đột.
- Xác nhận thư viện cần thiết có mặt trong artifact cuối cùng.
- Kiểm tra các API đã deprecated hoặc thay đổi chữ ký.
- Chạy test liên quan đến serialization, persistence, HTTP, security và tích hợp.
- Ghi lại workaround hoặc cấu hình tương thích tạm thời nếu chưa thể loại bỏ ngay.

Không nên giữ workaround vĩnh viễn mà không có chủ sở hữu và thời hạn xem xét. Mỗi workaround cần nêu lý do, phạm vi tác động, cách phát hiện khi không còn cần thiết và điều kiện gỡ bỏ.

### 6.4. Sửa mã nguồn và cấu hình

Khi compiler hoặc runtime chỉ ra API không còn phù hợp, hãy sửa theo hướng được hỗ trợ chính thức. Tránh thay một API cũ bằng API mới chỉ để làm mất lỗi compile mà không kiểm tra ngữ nghĩa. Cần xác nhận hành vi mới đáp ứng yêu cầu nghiệp vụ, đặc biệt ở các vùng xử lý thời gian, mã hóa, bảo mật, transaction và đồng thời.

Với reflection hoặc truy cập nội bộ JDK, trước tiên xác định thư viện hay đoạn mã nào thực sự cần quyền truy cập. Ưu tiên nâng thư viện hoặc dùng API công khai. Chỉ sử dụng tùy chọn mở module/package khi có lý do rõ ràng, phạm vi hẹp và kế hoạch loại bỏ; mở rộng quyền truy cập toàn cục có thể che giấu vấn đề tương thích và làm yếu ranh giới bảo mật.

Rà soát cấu hình JVM và ứng dụng sau khi nâng cấp. Một tùy chọn JVM có thể đã bị loại bỏ, đổi ý nghĩa hoặc không còn cần thiết. Cấu hình heap, GC, thread pool, timeout, TLS, logging và health check cần được kiểm chứng trên môi trường đích.

### 6.5. Giữ thay đổi có thể truy nguyên

Mỗi commit nên thể hiện một nhóm thay đổi có lý do rõ ràng. Không trộn nâng JDK với tái cấu trúc nghiệp vụ lớn nếu không cần thiết, vì khi test lỗi sẽ khó xác định nguyên nhân. Ghi lại dependency được nâng, cấu hình bị đổi, API được thay thế và kết quả kiểm tra liên quan. Nếu phải thay đổi đồng thời nhiều lớp, hãy ghi rõ quan hệ phụ thuộc và bằng chứng cho cả tổ hợp.

## 7. Kiểm chứng tương thích theo nhiều lớp

Kiểm chứng phải trả lời được bốn câu hỏi: dự án có build được không, ứng dụng có chạy được không, hành vi có còn đúng không và hệ thống có vận hành ổn định không. Không một loại test đơn lẻ nào trả lời đầy đủ cả bốn câu hỏi.

### 7.1. Kiểm tra tĩnh và kiểm tra build

Các cổng kiểm tra ban đầu gồm:

- Compile toàn bộ module nằm trong phạm vi, kể cả module không được gọi trực tiếp ở luồng chạy chính.
- Chạy annotation processor, code generation và tác vụ đóng gói.
- Chạy static analysis, kiểm tra API deprecated và rà soát truy cập JDK nội bộ.
- Kiểm tra dependency tree, dependency convergence và nội dung artifact.
- Xác nhận artifact có bytecode và API đích phù hợp với runtime tối thiểu đã cam kết.

Các công cụ như `jdeps` có thể hỗ trợ tìm phụ thuộc giữa class/package và tham chiếu tới API nội bộ của JDK; `jdeprscan` có thể hỗ trợ phát hiện API đã deprecated trong bytecode. Ví dụ:

```bash
jdeps --jdk-internals app.jar
jdeprscan --release 21 app.jar
```

Các lệnh này chỉ là công cụ hỗ trợ. Kết quả có thể cần classpath phù hợp, và không chứng minh rằng ứng dụng sẽ chạy đúng. Hãy xem chúng như một nguồn bằng chứng bên cạnh compiler, test và kiểm thử runtime.

### 7.2. Unit test và kiểm thử thành phần

Chạy unit test trên JDK đích để phát hiện khác biệt trong xử lý dữ liệu, collection, thời gian, encoding, exception và logic nghiệp vụ. Kiểm thử thành phần nên bao gồm các framework hoặc adapter mà ứng dụng dùng thật, chẳng hạn mapper, validator, serializer, repository và client HTTP.

Nếu test hiện tại phụ thuộc vào thứ tự chạy, thời gian hệ thống, timezone máy hoặc dữ liệu chia sẻ, cần làm rõ các giả định đó. Một test chỉ chạy ổn trên máy của tác giả có thể không đủ tin cậy để làm cổng phát hành.

### 7.3. Integration test và contract test

Chạy ứng dụng với các hệ thống mà nó thực sự tích hợp: database, message broker, cache, dịch vụ HTTP, identity provider và các dịch vụ nội bộ. Dùng phiên bản driver và cấu hình tương đương môi trường mục tiêu.

Kiểm tra cả đường thành công lẫn đường lỗi:

- Kết nối, xác thực, transaction và đóng kết nối.
- Timeout, retry, circuit breaker và xử lý phản hồi bất thường.
- Contract request/response, JSON/XML, header, status code và encoding.
- Schema, migration dữ liệu và khả năng tương thích giữa phiên bản ứng dụng cũ/mới.
- Tính lặp lại của thao tác khi có retry hoặc xử lý message nhiều lần.

Contract test giúp phát hiện thay đổi giao thức giữa các hệ thống mà unit test nội bộ không nhìn thấy.

### 7.4. Kiểm thử khởi động và hành vi runtime

Đóng gói ứng dụng đúng như cách sẽ phát hành, sau đó chạy artifact trên runtime đích. Không chỉ chạy từ IDE hoặc classpath của Gradle/Maven, vì classpath phát triển có thể khác artifact triển khai.

Xác minh:

- Ứng dụng khởi động, nạp cấu hình và đăng ký thành phần thành công.
- Health check và readiness chỉ báo sẵn sàng khi các phụ thuộc bắt buộc đã đáp ứng.
- Request, scheduled job, message consumer và tác vụ nền hoạt động đúng.
- Shutdown có trật tự, hoàn tất hoặc hủy tác vụ đúng cách và giải phóng tài nguyên.
- Log, metric, trace và thông tin lỗi vẫn có thể quan sát được.
- Không có lỗi linkage, class loading, reflection hoặc cảnh báo quan trọng bị bỏ qua.

### 7.5. Kiểm thử hiệu năng và độ ổn định

So sánh với baseline trên cùng loại dữ liệu, tải và cấu hình càng nhiều càng tốt. Theo dõi ít nhất:

- Thời gian khởi động và thời gian đạt trạng thái sẵn sàng.
- Throughput, latency trung bình và các percentile quan trọng.
- CPU, heap, non-heap, allocation, GC pause và số thread.
- Connection pool, hàng đợi, timeout và tỷ lệ lỗi.
- Mức sử dụng file descriptor, socket và tài nguyên hệ điều hành nếu có liên quan.

Chạy tải ngắn để phát hiện regression rõ rệt, sau đó chạy tải kéo dài hoặc soak test cho hệ thống có yêu cầu ổn định cao. Một lần test thành công trong vài phút không chứng minh rằng ứng dụng không rò rỉ bộ nhớ hoặc cạn tài nguyên sau nhiều giờ.

Không kết luận chỉ dựa trên một con số tổng hợp. Hãy so sánh theo cùng điều kiện và đặt ngưỡng chấp nhận trước khi chạy. Nếu hiệu năng thay đổi đáng kể, cần xác định nguyên nhân trước khi phát hành hoặc có quyết định chấp nhận rủi ro được ghi nhận.

### 7.6. Kiểm tra bảo mật và cấu hình vận hành

JDK mới có thể thay đổi chính sách TLS, chứng thư, thuật toán mật mã hoặc cách xử lý giao thức cũ. Hãy kiểm tra xác thực, phân quyền, kết nối TLS, secret loading, quyền file và các JVM option liên quan. Chạy kiểm tra dependency vulnerability theo chính sách của dự án và xem xét các cảnh báo mới xuất hiện sau khi cập nhật.

Kiểm tra trên container hoặc máy chủ thật sự sẽ chạy ứng dụng. Xác nhận image có đúng runtime, timezone, CA certificates, locale, user/permission, giới hạn CPU/bộ nhớ và cấu hình mạng. Một bài test chạy trên JDK cài ở máy lập trình viên không thay thế được kiểm tra artifact trong image phát hành.

## 8. Đánh giá kết quả và quyết định phát hành

Trước khi tạo release candidate, tổng hợp kết quả theo từng tiêu chí thay vì chỉ ghi “test pass”. Một bảng kiểm chứng có thể gồm:

| Tiêu chí | Bằng chứng cần lưu | Điều kiện đạt |
|---|---|---|
| Môi trường build | Log JDK, Wrapper, plugin và cấu hình compiler | Đúng phiên bản đã chốt, build tái lập được |
| Biên dịch và đóng gói | Log compile, test, package và thông tin artifact | Tất cả module trong phạm vi hoàn tất |
| Dependency | Dependency tree, danh sách phiên bản và kiểm tra bảo mật | Không còn xung đột hoặc vấn đề chưa được chấp nhận |
| Khởi động | Log startup, health/readiness và cấu hình runtime | Ứng dụng khởi động ổn định trên runtime đích |
| Hành vi nghiệp vụ | Kết quả unit, integration, contract và regression test | Các luồng bắt buộc giữ đúng hợp đồng |
| Hiệu năng | Báo cáo so sánh với baseline | Nằm trong ngưỡng đã thống nhất hoặc có ngoại lệ được duyệt |
| Vận hành | Log, metric, trace, shutdown và kiểm tra tài nguyên | Có thể giám sát và xử lý sự cố |
| Phục hồi | Kịch bản rollback và kết quả diễn tập nếu cần | Có thể quay về trạng thái an toàn trong giới hạn đã xác định |

Các lỗi còn mở phải được phân loại và có quyết định rõ ràng. Không được coi “chưa tái hiện” là “đã sửa”, hoặc “không có test” là “không có lỗi”. Nếu chấp nhận một rủi ro còn tồn tại, cần ghi phạm vi ảnh hưởng, lý do chấp nhận, biện pháp giảm thiểu, người phê duyệt và thời hạn xem xét lại.

Release candidate phải gắn với một commit và bộ artifact xác định. Lưu checksum, phiên bản dependency, cấu hình cần thiết và kết quả kiểm chứng để có thể truy nguyên chính xác bản nào đã được phát hành. Nếu build lại cùng commit nhưng artifact khác nhau, cần tìm nguyên nhân trước khi coi quy trình là tái lập được.

## 9. Phát hành theo từng bước và chuẩn bị quay lui

Không nên chuyển toàn bộ lưu lượng sang runtime mới ngay khi test ở môi trường kiểm thử thành công. Hãy chọn chiến lược phù hợp với kiến trúc và khả năng kiểm soát lưu lượng:

- **Canary:** đưa một phần nhỏ lưu lượng hoặc một nhóm instance sang bản mới, theo dõi rồi tăng dần.
- **Rolling deployment:** thay instance theo từng đợt, duy trì đủ năng lực phục vụ trong lúc chuyển đổi.
- **Blue-green:** chuẩn bị môi trường mới song song, xác minh trước rồi chuyển lưu lượng khi đạt điều kiện.
- **Phát hành theo module/dịch vụ:** chia phạm vi theo ranh giới độc lập để giới hạn ảnh hưởng.

Trong từng giai đoạn, theo dõi tỷ lệ lỗi, latency, CPU, memory, GC, số lần restart, health check và lỗi kết nối. So sánh với baseline hoặc nhóm instance chưa di chuyển. Đặt trước ngưỡng dừng: ví dụ tỷ lệ lỗi vượt ngưỡng, health check thất bại, latency tăng bất thường hoặc xuất hiện lỗi dữ liệu. Khi chạm ngưỡng, dừng tăng lưu lượng và thực hiện quy trình xử lý đã chuẩn bị.

### 9.1. Thiết kế rollback thực tế

Rollback cần được thiết kế trước phát hành, không phải bắt đầu viết khi production đã gặp sự cố. Cần xác định:

- Artifact và cấu hình của phiên bản trước được lưu ở đâu và có thể khôi phục trong bao lâu.
- Ai có quyền quyết định rollback và ai thực hiện.
- Điều kiện kích hoạt, thời gian phản ứng và cách xác nhận phục hồi.
- Log, metric và dữ liệu nào cần giữ lại để điều tra sau rollback.
- Những thay đổi nào không thể đảo ngược tự động.

Đặc biệt, thay đổi schema hoặc dữ liệu cần tương thích giữa ứng dụng cũ và mới. Có thể dùng cách mở rộng rồi thu hẹp (expand/contract): thêm cấu trúc mới theo cách phiên bản cũ vẫn hoạt động, chuyển ứng dụng và dữ liệu theo từng bước, chỉ xóa cấu trúc cũ sau khi đã xác nhận không còn phiên bản nào phụ thuộc. Nếu migration dữ liệu không thể đảo ngược, rollback ứng dụng đơn thuần có thể không đủ; phải có kế hoạch khôi phục dữ liệu riêng.

### 9.2. Hoàn tất phát hành

Khi rollout đạt tiêu chí ổn định:

- Ghi phiên bản JDK, framework, dependency và môi trường đã phát hành.
- Lưu commit, artifact checksum, kết quả test và quyết định ngoại lệ.
- Cập nhật ma trận tương thích từ trạng thái dự kiến sang trạng thái đã kiểm chứng.
- Cập nhật runbook, hướng dẫn phát triển, cấu hình CI và tài liệu xử lý sự cố.
- Ghi nhận workaround còn tồn tại cùng người phụ trách và thời hạn gỡ bỏ.
- Theo dõi lỗi sau phát hành trong khoảng thời gian phù hợp với đặc tính tải của hệ thống.

Chỉ gỡ bỏ cơ chế tương thích tạm thời sau khi đã xác nhận không còn instance hoặc quy trình nào phụ thuộc vào nó. Việc dọn dẹp nên là công việc có kiểm soát và có thể truy nguyên.

## 10. Ví dụ xuyên suốt: một dependency không tương thích với runtime đích

Giả sử một ứng dụng Java đang dùng thư viện X để tạo proxy. Khi chạy trên runtime đích, ứng dụng khởi động thất bại vì thư viện X truy cập một package nội bộ của JDK mà runtime mới không cho phép theo cách cũ.

Quy trình xử lý nên diễn ra như sau:

1. **Ghi nhận baseline:** lưu commit, JDK hiện tại, phiên bản thư viện X, cây dependency và log khởi động trên môi trường cũ.
2. **Tái hiện trên đích:** chạy đúng artifact với runtime đích và lưu stack trace. Không chỉ thử một đoạn code riêng nếu lỗi phụ thuộc vào framework hoặc classpath của ứng dụng.
3. **Truy nguyên:** xác định thư viện X là dependency trực tiếp hay bắc cầu, module nào gọi nó và phiên bản nào bắt đầu hỗ trợ runtime đích.
4. **Đối chiếu ma trận:** kiểm tra phiên bản X tương thích với JDK, framework và các dependency liên quan hay không.
5. **Chọn cách xử lý:** ưu tiên nâng X lên phiên bản được hỗ trợ hoặc thay thế bằng cơ chế công khai. Nếu buộc phải dùng tùy chọn mở package tạm thời, giới hạn phạm vi, ghi nhận rủi ro và kế hoạch loại bỏ.
6. **Kiểm chứng:** chạy compile, unit test, test tạo proxy, integration test và smoke test trên runtime đích. Kiểm tra cả luồng sử dụng proxy trong production, không chỉ xác nhận ứng dụng đã khởi động.
7. **Phát hành:** đưa artifact vào môi trường thử nghiệm, theo dõi lỗi khởi động và hành vi runtime, sau đó rollout theo chiến lược đã chọn.
8. **Đóng vấn đề:** lưu bằng chứng, cập nhật dependency matrix và đóng mục rủi ro khi tiêu chí hoàn thành đã được đáp ứng.

Ví dụ này cho thấy lỗi được phát hiện ở runtime có thể bắt nguồn từ một dependency bắc cầu. Chỉ sửa mã nguồn ứng dụng hoặc thêm một JVM option rộng có thể làm mất triệu chứng trước mắt nhưng không giải quyết nguyên nhân lâu dài.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách phòng tránh |
|---|---|---|
| Chỉ đổi JDK trên máy cá nhân | CI hoặc production vẫn dùng JDK khác | Khai báo và xác minh JDK ở từng môi trường |
| Chỉ kiểm tra compile | Bỏ sót lỗi linkage, cấu hình, tích hợp và hành vi runtime | Kiểm tra artifact trên runtime đích và chạy test nhiều lớp |
| Chỉ xem dependency trực tiếp | Bỏ sót thư viện bắc cầu hoặc phiên bản bị ép chọn | Lưu dependency tree và truy nguyên thư viện quan trọng |
| Nâng tất cả dependency lên phiên bản mới nhất | Tạo tổ hợp chưa được hỗ trợ, tăng phạm vi thay đổi | Dựa vào ma trận tương thích và cập nhật theo nhóm có kiểm soát |
| Bỏ qua plugin build | Build hỏng dù mã ứng dụng tương thích | Kiểm tra Wrapper, plugin và tác vụ CI thực tế |
| Dùng workaround toàn cục | Che giấu lỗi và mở rộng phạm vi rủi ro | Ưu tiên API công khai, giới hạn workaround và đặt hạn gỡ bỏ |
| Không có baseline | Không biết regression có xuất hiện sau di chuyển hay đã tồn tại | Lưu commit, log, test và số liệu trước thay đổi |
| Kiểm thử trên môi trường khác production | Kết quả tốt giả tạo do khác runtime, image hoặc cấu hình | Dùng môi trường đại diện và xác minh artifact cuối |
| Không chuẩn bị rollback | Sự cố kéo dài hoặc không thể phục hồi nhanh | Chốt điều kiện, quyền hạn, artifact và dữ liệu phục hồi trước phát hành |

## 12. Hồ sơ hoàn thành một đợt migration

Một đợt di chuyển có thể được bàn giao và kiểm toán khi có đủ các đầu ra sau:

1. **Baseline:** commit gốc, kiểm kê JDK/build tool/framework/dependency, cấu hình môi trường và kết quả kiểm thử ban đầu.
2. **Compatibility matrix:** tổ hợp phiên bản đích, nguồn xác nhận hỗ trợ và trạng thái kiểm chứng của từng thành phần.
3. **Gap/risk register:** các vấn đề phát hiện được, mức ưu tiên, bằng chứng, chủ sở hữu, hướng xử lý và tiêu chí đóng.
4. **Migration plan:** thứ tự công việc, quan hệ phụ thuộc, phạm vi module, checkpoint và điều kiện dừng.
5. **Change record:** commit hoặc pull request liên quan, dependency/configuration đã thay đổi và lý do.
6. **Verification report:** log build, kết quả test, kiểm tra runtime, hiệu năng, bảo mật và môi trường triển khai.
7. **Release record:** phiên bản, artifact, checksum, thời điểm, chiến lược rollout và người xác nhận.
8. **Recovery plan:** điều kiện rollback, artifact/cấu hình trước đó, quy trình phục hồi dữ liệu và kết quả diễn tập nếu có.
9. **Follow-up:** rủi ro được chấp nhận, workaround còn tồn tại, việc cần dọn dẹp và thời hạn theo dõi sau phát hành.

### Checklist trước khi đóng đợt di chuyển

- [ ] Đã xác định rõ JDK chạy build, JDK biên dịch, mức API đích và runtime chạy ứng dụng.
- [ ] Đã kiểm kê dependency trực tiếp, bắc cầu, plugin, framework và các module liên quan.
- [ ] Đã có ma trận tương thích và nguồn bằng chứng cho các thành phần quan trọng.
- [ ] Các vấn đề chặn phát hành đã được xử lý hoặc có quyết định ngoại lệ được phê duyệt.
- [ ] Build và đóng gói thành công trên cấu hình đã chốt.
- [ ] Unit, integration, contract và regression test của các luồng quan trọng đạt yêu cầu.
- [ ] Artifact cuối đã chạy trên runtime và môi trường triển khai đại diện.
- [ ] Hiệu năng, bảo mật, khả năng quan sát và shutdown đã được kiểm chứng theo tiêu chí dự án.
- [ ] Có artifact, checksum, commit và báo cáo để truy nguyên release.
- [ ] Có chiến lược rollout, ngưỡng dừng và phương án rollback khả thi.
- [ ] Ma trận tương thích, runbook và tài liệu vận hành đã được cập nhật.
- [ ] Rủi ro còn lại có người phụ trách, biện pháp giảm thiểu và thời hạn xem xét.

Một đợt Java compatibility migration chỉ hoàn tất khi nhóm chứng minh được tổ hợp phiên bản đích hoạt động đúng trong điều kiện dự kiến, có thể phát hành và có thể phục hồi khi cần. Kiểm kê giúp biết điểm xuất phát; ma trận và sổ rủi ro biến khác biệt thành công việc cụ thể; kiểm chứng cung cấp bằng chứng; còn phát hành có kiểm soát đưa kết quả vào vận hành với giới hạn rủi ro đã được thống nhất.
