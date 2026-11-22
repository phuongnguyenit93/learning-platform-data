# Thế nào là một build đúng, có thể lặp lại và dễ chẩn đoán

Trong một dự án Java, build là quá trình biến mã nguồn, tài nguyên, cấu hình và các dependency thành những đầu ra có thể sử dụng được: class đã biên dịch, JAR, báo cáo kiểm thử, tài liệu hoặc các artifact khác. Một lệnh build kết thúc với mã thoát `0` là tín hiệu tốt, nhưng chưa đủ để kết luận hệ thống build đáng tin cậy. Ta còn cần biết đầu ra có đúng với mục tiêu hay không, lần chạy sau có tái tạo được kết quả hay không, và khi có lỗi thì có thể xác định nguyên nhân từ bằng chứng rõ ràng hay không.

Ba thuộc tính này bổ sung cho nhau:

- **Đúng (correct):** build thực hiện đúng yêu cầu, dùng đúng mã nguồn và cấu hình, áp dụng đúng dependency, chạy đúng các bước kiểm tra, đồng thời tạo ra artifact có nội dung và đặc tính mong đợi.
- **Có thể lặp lại (repeatable):** cùng một đầu vào đã xác định, trong cùng điều kiện được kiểm soát, có thể chạy build nhiều lần và nhận được kết quả tương đương. Nếu yêu cầu reproducible theo nghĩa chặt, artifact tạo ra phải giống hệt về byte.
- **Dễ chẩn đoán (diagnosable):** khi build thất bại hoặc tạo ra kết quả sai, log, task graph, báo cáo và thông tin môi trường đủ rõ để khoanh vùng bước lỗi, nguyên nhân và cách tái hiện.

Một build tốt cần cả ba. Build đúng một lần nhưng lần sau cho kết quả khác là rủi ro. Build luôn chạy xanh nhưng bỏ qua test hoặc đóng gói nhầm module cũng không đúng. Build có thể tái hiện lỗi nhưng chỉ in một thông báo chung chung thì vẫn tốn nhiều thời gian điều tra.

## 1. Build đúng bắt đầu từ việc xác định đúng đầu vào và đầu ra

Build không chỉ phụ thuộc vào các file `.java`. Kết quả thường chịu ảnh hưởng của nhiều đầu vào:

| Nhóm đầu vào | Ví dụ | Câu hỏi cần kiểm soát |
|---|---|---|
| Mã nguồn | `src/main/java`, `src/test/java` | Đang build đúng commit và đúng module chưa? |
| Tài nguyên | `src/main/resources`, file cấu hình | Tài nguyên nào được đưa vào classpath hoặc artifact? |
| Build logic | `settings.gradle`, `build.gradle`, convention plugin | Quy tắc nào quyết định task và dependency? |
| Dependency | Thư viện Maven, Gradle plugin, project dependency | Phiên bản được chọn có xác định và hợp lệ không? |
| Toolchain | JDK, Gradle Wrapper, compiler | Có đúng phiên bản công cụ mà dự án yêu cầu không? |
| Môi trường | OS, biến môi trường, system property | Có giá trị bên ngoài nào làm thay đổi kết quả không? |
| Tham số chạy | task, property, profile, flag | Lệnh có thực hiện đúng mục tiêu mong muốn không? |

Đầu ra cũng cần được định nghĩa. Ví dụ, `test` thành công chỉ chứng minh các test thuộc task đó đã chạy và vượt qua theo cấu hình hiện tại. Nó không tự chứng minh rằng `bootJar` đã được tạo, rằng JAR chứa đúng tài nguyên, hoặc rằng module khác cũng build được.

Vì vậy, trước khi đánh giá kết quả, hãy viết rõ mục tiêu:

```text
Đầu vào: commit hiện tại, JDK 21, Gradle Wrapper của repository
Phạm vi: module orders-api
Yêu cầu: biên dịch production code, chạy unit test, đóng gói executable JAR
Đầu ra cần có: test report và boot JAR của orders-api
Điều kiện: không bỏ qua test, không dùng dependency động ngoài kiểm soát
```

Mục tiêu cụ thể giúp chọn đúng task, đọc đúng kết quả và tránh kết luận quá rộng từ một lệnh build hẹp.

## 2. Các tiêu chí của một build đúng

### 2.1. Chọn đúng project và task

Trong Gradle multi-project, tên task có thể xuất hiện ở nhiều project. Chạy `test` ở root có thể kích hoạt nhiều task `test`; chạy `:orders-api:test` chỉ rõ phạm vi một project. Khi cần build một module cụ thể, dùng task path đầy đủ để tránh nhầm phạm vi:

```bash
./gradlew :orders-api:clean :orders-api:test :orders-api:bootJar
```

Trên Windows có thể dùng wrapper tương ứng:

```powershell
.\gradlew.bat :orders-api:clean :orders-api:test :orders-api:bootJar
```

Không phải dự án nào cũng có `bootJar`; module library có thể chỉ tạo JAR thông thường. Hãy kiểm tra loại project và task thực tế trước khi dùng một lệnh mẫu.

### 2.2. Không bỏ qua bước xác minh cần thiết

Một build chỉ được xem là đúng khi đã thực hiện đủ các bước theo yêu cầu. Ví dụ:

- `compileJava` kiểm tra biên dịch mã nguồn production.
- `test` chạy test được gắn với task đó.
- `check` thường gom các kiểm tra chất lượng mà plugin và build logic đã cấu hình.
- `jar` hoặc `bootJar` đóng gói artifact theo loại module.

`-x test` loại task test khỏi execution graph. `-DskipTests` hoặc một property riêng của plugin có thể thay đổi hành vi kiểm thử tùy dự án. Những lựa chọn này hữu ích trong một số workflow có chủ đích, nhưng không thể dùng kết quả đó để tuyên bố rằng test đã pass.

Hãy phân biệt rõ ba trạng thái:

1. **PASS:** bước cần thiết đã chạy và hoàn tất thành công.
2. **SKIPPED:** bước không chạy, do up-to-date, điều kiện task, cấu hình hoặc lệnh loại trừ. Cần hiểu lý do trước khi kết luận.
3. **FAILED:** bước đã chạy và thất bại; cần giữ lại lỗi gốc và bằng chứng liên quan.

### 2.3. Xác minh artifact, không chỉ nhìn dòng BUILD SUCCESSFUL

Sau khi build, kiểm tra artifact có thực sự tồn tại ở vị trí mong đợi, có kích thước hợp lý và có nội dung phù hợp. Ví dụ với JAR:

```bash
jar tf build/libs/orders-api.jar
```

Có thể kiểm tra manifest:

```bash
unzip -p build/libs/orders-api.jar META-INF/MANIFEST.MF
```

Tên file thực tế có thể chứa version hoặc classifier. Đừng giả định đường dẫn artifact khi chưa kiểm tra cấu hình task. Với Spring Boot executable JAR, cấu trúc thường có các thành phần như `BOOT-INF/classes` và `BOOT-INF/lib`; JAR library thông thường có cấu trúc khác.

Nếu yêu cầu là chạy được, có thể thực hiện smoke test ở môi trường phù hợp:

```bash
java -jar build/libs/orders-api.jar
```

Smoke test chỉ xác nhận một luồng khởi động cơ bản trong môi trường thử nghiệm; nó không thay thế unit test, integration test hoặc kiểm tra hành vi nghiệp vụ.

## 3. Build có thể lặp lại

Một lần chạy thành công chỉ là một quan sát. Khả năng lặp lại đòi hỏi xác định được những yếu tố có thể làm kết quả thay đổi và kiểm soát chúng.

### 3.1. Khóa phiên bản công cụ

Gradle Wrapper (`gradlew`, `gradlew.bat` và `gradle/wrapper/gradle-wrapper.properties`) giúp mọi thành viên dùng cùng phiên bản Gradle được dự án chỉ định. Hãy gọi wrapper của repository thay vì phụ thuộc vào Gradle cài toàn cục:

```bash
./gradlew --version
java -version
```

Đối với Java, cần phân biệt JDK dùng để chạy Gradle với Java toolchain dùng để biên dịch hoặc chạy test. Cấu hình toolchain giúp yêu cầu một phiên bản compiler cụ thể, nhưng máy chạy build vẫn phải có khả năng cung cấp toolchain đó, tải về theo cấu hình hoặc trỏ tới một installation hợp lệ.

Ví dụ cấu hình toolchain trong Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đây là ví dụ minh họa; hãy theo cấu hình hiện hành của dự án. Không tự ý thay JDK chỉ vì máy cá nhân đang có phiên bản khác.

### 3.2. Quản lý dependency có kiểm soát

Dependency ảnh hưởng trực tiếp tới classpath và artifact. Một khai báo phiên bản động như `2.+`, `latest.release` hoặc một snapshot có thể resolve thành phiên bản khác ở những thời điểm khác nhau. Khi cần tính ổn định cao, hãy ưu tiên phiên bản cụ thể và cân nhắc Gradle dependency locking:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi bật locking, dự án cần tạo và quản lý lock state theo workflow đã thống nhất. Lockfile phải được cập nhật có chủ đích khi nâng dependency; không nên xóa lockfile để “sửa” một build đang lỗi.

Dependency verification có thể kiểm tra checksum hoặc chữ ký của artifact đã tải về. Nó giúp phát hiện artifact thay đổi ngoài dự kiến, nhưng cần thiết lập và duy trì metadata xác minh đúng cách.

### 3.3. Tránh đầu vào ẩn và hành vi không xác định

Một build khó lặp lại khi kết quả phụ thuộc vào trạng thái máy mà không được ghi nhận, ví dụ:

- Đọc file nằm ngoài repository mà không khai báo.
- Dựa vào biến môi trường cá nhân hoặc system property chưa được tài liệu hóa.
- Dùng thời gian hiện tại, số ngẫu nhiên hoặc thứ tự duyệt file không ổn định để sinh nội dung.
- Ghi output vào một thư mục dùng chung khiến lần chạy trước ảnh hưởng lần chạy sau.
- Tải một script hoặc dependency không khóa phiên bản trong lúc build.
- Dựa vào cache cũ che giấu đầu vào đã thay đổi.

Gradle incremental build và build cache giúp tiết kiệm thời gian bằng cách tái sử dụng kết quả khi đầu vào được mô tả chính xác. Chúng không phải bằng chứng tự động rằng task được khai báo đúng. Nếu task tùy biến đọc thêm một file nhưng không khai báo input, Gradle có thể coi task vẫn up-to-date dù nội dung cần xử lý đã đổi.

Với task tùy biến, hãy khai báo input và output bằng các annotation hoặc property API phù hợp, chẳng hạn `@InputFile`, `@Input`, `@OutputDirectory`. Không đọc trạng thái tùy tiện từ filesystem hoặc môi trường trong action mà bỏ qua mô hình input/output của Gradle.

### 3.4. Phân biệt repeatable và reproducible

Hai thuật ngữ thường được dùng gần nhau nhưng mức yêu cầu khác nhau:

| Thuộc tính | Ý nghĩa | Ví dụ kiểm chứng |
|---|---|---|
| Repeatable build | Chạy lại trong điều kiện được kiểm soát cho kết quả tương đương | Cùng test pass, cùng danh sách dependency và cùng nội dung logic của artifact |
| Reproducible artifact | Các lần build độc lập tạo artifact giống hệt từng byte | So sánh SHA-256 của hai JAR được tạo từ cùng source và môi trường chuẩn hóa |

Artifact có thể khác byte vì timestamp, thứ tự entry trong archive, đường dẫn tuyệt đối được ghi vào metadata hoặc thông tin build được chèn vào manifest. Muốn đạt reproducible artifact, cần chuẩn hóa các yếu tố đó và kiểm chứng bằng hash. Không nên tuyên bố build reproducible chỉ vì hai lần chạy đều thành công.

Ví dụ so sánh checksum trên các hệ thống có `sha256sum`:

```bash
sha256sum build/libs/orders-api.jar
```

Trên PowerShell:

```powershell
Get-FileHash .\build\libs\orders-api.jar -Algorithm SHA256
```

So sánh có ý nghĩa khi hai artifact được tạo từ cùng commit, cùng cấu hình, cùng dependency resolution và điều kiện môi trường đã xác định. Nếu các điều kiện khác nhau, hash khác nhau chưa đủ để kết luận build không reproducible.

## 4. Build dễ chẩn đoán

Chẩn đoán tốt là khả năng trả lời nhanh bốn câu hỏi: task nào lỗi, lỗi ở giai đoạn nào, lỗi do đầu vào hay do thực thi, và có thể tái hiện bằng lệnh nào?

### 4.1. Đọc log theo thứ tự

Khi Gradle báo lỗi, bắt đầu từ:

1. Task thất bại, ví dụ `:orders-api:compileJava` hay `:orders-api:test`.
2. Loại exception và thông báo nguyên nhân gần nhất.
3. `Caused by` đầu tiên có ý nghĩa, thay vì chỉ nhìn dòng cuối cùng.
4. File, class, dependency hoặc cấu hình được nêu trong stack trace.
5. Những task trước đó đã chạy thành công hay bị skip.

Các cờ hữu ích:

```bash
# Hiển thị thông tin tổng quát hơn
./gradlew :orders-api:test --info

# Hiển thị stack trace của lỗi
./gradlew :orders-api:test --stacktrace

# Kết hợp thông tin và stack trace khi cần
./gradlew :orders-api:test --info --stacktrace
```

`--debug` tạo log rất chi tiết và có thể chứa thông tin nhạy cảm từ môi trường hoặc cấu hình. Chỉ bật khi thật sự cần, kiểm tra nội dung trước khi chia sẻ log ra ngoài.

### 4.2. Kiểm tra task graph và dependency

Nếu không chắc lệnh sẽ chạy task nào, dùng dry run:

```bash
./gradlew :orders-api:bootJar --dry-run
```

Dry run cho thấy task graph dự kiến, nhưng không thực thi task và không chứng minh artifact tạo được. Khi cần hiểu dependency được resolve, có thể dùng:

```bash
./gradlew :orders-api:dependencies --configuration runtimeClasspath
```

Để tìm lý do một dependency được chọn:

```bash
./gradlew :orders-api:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
```

Các lệnh này giúp phân biệt lỗi do source code với lỗi do dependency graph, version conflict hoặc cấu hình project.

### 4.3. Dùng test report và build scan đúng cách

Gradle Test thường tạo báo cáo HTML/XML trong thư mục build của project. Báo cáo giúp biết test class nào thất bại, assertion nào không đúng và stack trace tại thời điểm test. Khi CI lưu test report làm artifact, người điều tra có thể xem kết quả mà không cần chạy lại ngay.

Build scan có thể cung cấp task timeline, dependency resolution, môi trường và hiệu năng chi tiết. Việc xuất bản scan có thể gửi dữ liệu build tới một dịch vụ bên ngoài; chỉ sử dụng theo chính sách của tổ chức và hiểu rõ dữ liệu được chia sẻ.

### 4.4. Giữ lại lệnh và bối cảnh tái hiện

Một báo cáo lỗi hữu ích nên ghi:

- Commit hoặc branch đang kiểm tra.
- Phiên bản JDK và Gradle Wrapper.
- OS hoặc môi trường CI liên quan.
- Lệnh chính xác đã chạy, bao gồm task và property.
- Task thất bại đầu tiên và thông báo lỗi gốc.
- Test report, stack trace hoặc artifact liên quan.
- Build có phụ thuộc service, secret hoặc biến môi trường nào không (chỉ ghi tên/nguồn, không ghi giá trị bí mật).

Không chỉ gửi ảnh chụp dòng `BUILD FAILED`. Người khác cần có đủ thông tin để chạy lại cùng một tình huống.

## 5. Quy trình thực hành để đánh giá một build

Có thể áp dụng quy trình sau khi kiểm tra một thay đổi hoặc điều tra một lỗi build.

### Bước 1: Xác nhận môi trường

```bash
git rev-parse --short HEAD
java -version
./gradlew --version
```

Ghi nhận commit, JVM và Gradle. Nếu dự án có toolchain, kiểm tra thêm cấu hình và JVM thực sự được task sử dụng.

### Bước 2: Xác định phạm vi

Xem project path, loại module và task cần thiết. Nếu chỉ cần xác minh một module, chạy task có project path rõ ràng. Nếu yêu cầu là toàn repository, dùng lifecycle task phù hợp của repository.

### Bước 3: Chạy build với các kiểm tra cần thiết

```bash
./gradlew :orders-api:clean :orders-api:check :orders-api:bootJar
```

`clean` hữu ích khi cần loại bỏ output cũ để kiểm tra từ trạng thái sạch. Nó không phải lúc nào cũng cần trong workflow hằng ngày; incremental build là một phần bình thường của Gradle. `check` chỉ bao gồm những verification task đã được gắn vào lifecycle của project.

### Bước 4: Xác minh kết quả

Kiểm tra exit code, task outcome, test report và artifact. Xác nhận đúng file được tạo, đúng project, đúng loại package và có nội dung mong đợi. Nếu cần, chạy smoke test trong môi trường an toàn.

### Bước 5: Chạy lại để kiểm tra tính ổn định

Chạy lại cùng lệnh trong điều kiện tương đương. Quan sát task nào là `UP-TO-DATE` hoặc `FROM-CACHE`, task nào thực thi lại và liệu kết quả có thay đổi ngoài dự kiến không. Nếu đang điều tra vấn đề cache, thử một lần với `--no-build-cache` hoặc trạng thái output sạch để so sánh; ghi rõ đây là phép thử có điều kiện khác.

### Bước 6: Lưu bằng chứng

Lưu lệnh, phiên bản công cụ, log cần thiết, test report và checksum artifact nếu yêu cầu mức reproducibility. Bằng chứng nên đủ để người khác hiểu phạm vi kết luận và tái hiện khi cần.

## 6. Những tình huống dễ gây kết luận sai

| Hiện tượng | Kết luận vội thường gặp | Cách kiểm tra đúng |
|---|---|---|
| Có `BUILD SUCCESSFUL` | Toàn bộ sản phẩm đã được xác minh | Xem task graph, task outcome và yêu cầu đầu ra |
| `test` là `UP-TO-DATE` | Test đã chạy lại ở lần này | Kiểm tra test report và lần chạy trước; up-to-date nghĩa là Gradle tái sử dụng output hợp lệ theo input đã khai báo |
| Build trên máy cá nhân pass | CI chắc chắn sẽ pass | So sánh JDK, OS, biến môi trường, dependency cache và service phụ thuộc |
| Xóa cache thì build chạy được | Cache luôn là nguyên nhân | Tìm input thiếu, dependency thay đổi hoặc trạng thái cũ; xóa cache chỉ là biện pháp chẩn đoán |
| Hai lần build đều pass | Artifact reproducible | So sánh đầu vào và hash artifact nếu cần byte-for-byte reproducibility |
| Không thấy lỗi trong log ngắn | Không có lỗi gốc | Mở stack trace, test report và log task thất bại đầu tiên |

Một điểm quan trọng: cache không làm build sai theo bản chất. Cache đáng tin khi task mô tả chính xác input/output và các task tuân thủ contract đó. Nếu task có side effect hoặc phụ thuộc trạng thái ẩn, cache có thể làm lỗi khó nhận ra hơn.

## 7. Ví dụ: phân tích một build không ổn định

Giả sử một module đôi lúc pass, đôi lúc fail ở `processResources`. Log cho thấy file cấu hình được sinh ra có giá trị timestamp khác nhau. Điều tra có thể tiến hành như sau:

1. Ghi nhận commit, JDK, Gradle Wrapper và lệnh chạy.
2. Xác định task tạo file cấu hình và nơi lấy timestamp.
3. Kiểm tra timestamp có phải dữ liệu nghiệp vụ cần thiết hay chỉ là metadata build.
4. Nếu không cần thời gian chạy thực tế, thay bằng giá trị được truyền vào rõ ràng hoặc bỏ metadata biến thiên.
5. Khai báo đầy đủ input/output cho task sinh file.
6. Chạy hai build sạch với cùng đầu vào, so sánh file sinh ra và checksum artifact.
7. Nếu kết quả vẫn khác, kiểm tra thêm thứ tự archive entry, manifest và các metadata khác.

Qua ví dụ này, ta thấy ba tiêu chí gắn với nhau: đầu ra phải đúng yêu cầu, đầu vào biến thiên phải được kiểm soát để lặp lại, và log/task model phải giúp xác định chính xác nơi tạo ra sai khác.

## 8. Checklist đánh giá

Trước khi nói một build đáng tin cậy, hãy tự kiểm tra:

- [ ] Đã xác định đúng commit, module, task và đầu ra cần tạo.
- [ ] Đã dùng đúng Gradle Wrapper và JDK/toolchain theo yêu cầu.
- [ ] Dependency và plugin được resolve theo quy tắc có thể kiểm soát.
- [ ] Các bước compile, test, check và packaging cần thiết đã thực sự chạy hoặc có lý do rõ ràng khi skip.
- [ ] Artifact tồn tại, thuộc đúng module và có cấu trúc mong đợi.
- [ ] Không có đầu vào ẩn hoặc trạng thái máy chưa được ghi nhận làm thay đổi kết quả.
- [ ] Task tùy biến khai báo input/output chính xác để incremental build và cache hoạt động đúng.
- [ ] Có thể chạy lại với cùng điều kiện và nhận kết quả tương đương.
- [ ] Nếu cần reproducible artifact, đã chuẩn hóa metadata và so sánh checksum.
- [ ] Khi lỗi xảy ra, có lệnh tái hiện, stack trace, test report và thông tin môi trường cần thiết.

Không phải dự án nào cũng cần byte-for-byte reproducibility cho mọi artifact. Mức yêu cầu phụ thuộc vào mục đích: build local để phát triển, CI để xác minh pull request, hay pipeline phát hành phần mềm. Tuy nhiên, mọi mức độ đều cần phạm vi rõ ràng, đầu vào có thể giải thích và bằng chứng đủ để hiểu kết quả.

## Kết luận

Một build đúng trả lời được câu hỏi **đã tạo đúng thứ cần tạo và đã kiểm tra đúng điều cần kiểm tra chưa**. Một build có thể lặp lại trả lời được **với cùng đầu vào, ta có thể nhận lại kết quả tương đương không**. Một build dễ chẩn đoán trả lời được **nếu kết quả sai, ta có thể tìm ra nguyên nhân và tái hiện nó bằng bằng chứng nào**. Khi thiết kế task, quản lý dependency, kiểm soát toolchain và lưu báo cáo theo ba tiêu chí này, build trở thành một phần đáng tin cậy của quy trình phát triển thay vì chỉ là một lệnh cần chạy cho đến khi thấy màu xanh.
