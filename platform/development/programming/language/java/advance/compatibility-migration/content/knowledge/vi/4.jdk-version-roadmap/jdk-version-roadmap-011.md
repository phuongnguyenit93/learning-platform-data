# Tách thay đổi bản vá bảo mật khỏi thay đổi major khi cần truy tìm nguyên nhân

## 1. Vì sao cần tách hai loại thay đổi?

Trong quá trình nâng cấp hệ sinh thái Java, nhóm thường phải xử lý đồng thời hai nhu cầu: vá một lỗ hổng bảo mật đang ảnh hưởng đến dependency hoặc runtime, và nâng cấp major version của JDK, framework hay thư viện để tiếp tục được hỗ trợ hoặc sử dụng khả năng mới. Hai nhu cầu này có thể xuất hiện cùng lúc, nhưng chúng có mục tiêu và mức độ rủi ro khác nhau.

**Bản vá bảo mật** nhằm loại bỏ hoặc giảm một lỗ hổng đã được xác định. Thay đổi cần thiết có thể rất nhỏ, chẳng hạn nâng một dependency từ bản vá cũ lên bản vá đã sửa CVE. **Thay đổi major** thường có phạm vi rộng hơn: API có thể bị loại bỏ, hành vi mặc định có thể đổi, dependency graph có thể được sắp xếp lại, namespace có thể chuyển từ `javax` sang `jakarta`, hoặc yêu cầu JDK/build tool có thể thay đổi.

Nếu gộp bản vá bảo mật và một migration major vào cùng một thay đổi lớn, khi hệ thống phát sinh lỗi sẽ khó xác định nguyên nhân. Lỗi có thể đến từ bản vá, thay đổi API, dependency transitive, cấu hình mới, compiler, runtime hay tương tác giữa nhiều thay đổi. Việc truy tìm nguyên nhân kéo dài có thể làm chậm cả xử lý bảo mật lẫn migration.

Tách thay đổi thành các phần độc lập giúp nhóm trả lời những câu hỏi quan trọng:

- Bản vá bảo mật có giải quyết đúng lỗ hổng mà không làm thay đổi hành vi ngoài dự kiến không?
- Migration major có gây lỗi riêng khi không có bản vá bảo mật đi kèm không?
- Nếu chỉ triển khai bản vá mà chưa nâng major, hệ thống có còn build, chạy và được hỗ trợ không?
- Nếu cần triển khai cả hai cùng lúc, bằng chứng nào cho thấy lỗi xuất hiện do bản vá, do migration hay do tương tác giữa chúng?
- Có thể rollback hoặc phát hành lại một phần thay đổi mà không tạo ra trạng thái bảo mật không an toàn không?

Mục tiêu của việc tách là giữ được khả năng truy vết và khoanh vùng nguyên nhân. Việc triển khai có thể diễn ra ở hai đợt riêng hoặc trong cùng một đợt phát hành, tùy mức độ khẩn cấp và ràng buộc kỹ thuật. Điều quan trọng là từng nhóm thay đổi phải có phạm vi, bằng chứng và tiêu chí chấp nhận riêng.

## 2. Phân biệt bản vá bảo mật và thay đổi major

### 2.1. Bản vá bảo mật

Bản vá bảo mật là thay đổi được thực hiện để khắc phục một điểm yếu hoặc lỗ hổng. Nó có thể nằm trong patch release, minor release, một bản cập nhật vendor, một bản backport hoặc một phiên bản thư viện mới hơn. Không phải mọi nhà cung cấp đều dùng cùng quy tắc versioning, vì vậy không thể chỉ nhìn số phiên bản để kết luận mức độ thay đổi.

Thông tin cần xác minh trước khi chọn bản vá:

- Mã định danh lỗ hổng (ví dụ CVE), mức độ nghiêm trọng và điều kiện khai thác.
- Artifact, module và các phiên bản bị ảnh hưởng; bao gồm dependency bắc cầu.
- Phiên bản đã sửa được nhà cung cấp công bố và nhánh phát hành còn được hỗ trợ.
- Có bản vá backport cho nhánh hiện tại hay phải nâng lên minor/major mới.
- Thay đổi đi kèm ngoài phần sửa bảo mật: API, cấu hình, runtime requirement, dependency khác hoặc hành vi mặc định.
- Hướng dẫn migration, advisory, release notes và các giới hạn đã biết của bản vá.

Một bản vá có thể sửa lỗ hổng nhưng đồng thời thay đổi hành vi vì nó siết validation, loại bỏ thuật toán yếu, thay đổi TLS mặc định hoặc từ chối input trước đây được chấp nhận. Vì vậy, “security patch” không có nghĩa là “không có rủi ro tương thích”.

### 2.2. Thay đổi major

Major version thường là mốc có khả năng chứa thay đổi không tương thích, nhưng mức độ thay đổi thực tế phụ thuộc vào chính sách phát hành của từng dự án. Một số hệ sinh thái tuân theo Semantic Versioning khá chặt; một số nền tảng có quy tắc riêng hoặc thay đổi lớn trong minor release.

Các dấu hiệu cho thấy migration major có thể có phạm vi rộng:

- API public bị xóa, đổi chữ ký hoặc thay đổi semantics.
- Package/namespace thay đổi, ví dụ chuyển các API Jakarta EE từ `javax.*` sang `jakarta.*`.
- JDK tối thiểu, class-file target hoặc build tool tối thiểu thay đổi.
- Dependency BOM/platform thay đổi nhiều artifact cùng lúc.
- Cấu hình, auto-configuration, lifecycle, serialization, security hoặc transaction semantics thay đổi.
- Plugin, annotation processor, test engine, runtime container hoặc driver phải nâng đồng bộ.

Một major migration cần được đánh giá như một thay đổi nền tảng. Không nên xem nó là một bước “nâng số phiên bản” đơn giản.

### 2.3. Bảng so sánh mục tiêu và bằng chứng

| Khía cạnh | Bản vá bảo mật | Migration major |
| --- | --- | --- |
| Mục tiêu chính | Khắc phục lỗ hổng hoặc giảm rủi ro khai thác | Chuyển sang nền tảng/API/phiên bản mục tiêu |
| Phạm vi kỳ vọng | Có thể nhỏ, nhưng phải xác minh | Thường rộng hơn và có nhiều thành phần liên quan |
| Bằng chứng đầu vào | Security advisory, CVE, fixed version, dependency path | Migration guide, compatibility matrix, release notes |
| Rủi ro chính | Regression do thay đổi bảo mật hoặc dependency | Breaking API/behavior, build/runtime, schema và integration |
| Kiểm thử trọng tâm | Test đường khai thác, regression liên quan, dependency scan | Build, unit/integration/contract, runtime và vận hành |
| Điều kiện hoàn tất | Phiên bản đã sửa được sử dụng và lỗ hổng không còn hiện diện trong phạm vi đánh giá | Hệ thống đáp ứng hợp đồng và yêu cầu trên nền tảng mới |
| Rollback | Phải xem xét rủi ro quay về bản dễ bị khai thác | Phải xem xét bytecode, dữ liệu, schema và tương thích phiên bản |

Hai loại thay đổi có thể giao nhau. Ví dụ, nhà cung cấp chỉ phát hành bản sửa CVE trong major version mới. Khi đó nhóm phải đánh giá việc nâng major là một phần của phương án khắc phục bảo mật, thay vì giả định có thể tách hoàn toàn bằng cách chọn một patch version cũ.

## 3. Khi nào nên tách thay đổi?

Tách bản vá bảo mật và migration major đặc biệt hữu ích khi các điều kiện sau xuất hiện:

1. Có thể áp dụng bản vá bảo mật trên nhánh hiện tại mà không cần nâng major.
2. Major migration có nhiều thay đổi API, cấu hình hoặc dependency độc lập với CVE.
3. Khi lỗi xảy ra, nhóm cần xác định nhanh thay đổi nào gây ra regression.
4. Có thể kiểm thử riêng từng tập thay đổi trên cùng baseline.
5. Có thể tạo artifact hoặc commit riêng để so sánh, rollback và truy vết.
6. Thời hạn bảo mật và lịch migration major khác nhau.

Ví dụ, dịch vụ đang dùng Spring Boot 2.x và một thư viện HTTP có bản vá CVE trong cùng nhánh. Nhóm cũng dự định chuyển lên Spring Boot 3.x, Java 21 và Jakarta namespace. Nếu bản vá có thể dùng an toàn trên nhánh hiện tại, nên kiểm chứng và phát hành bản vá độc lập trước, sau đó thực hiện migration major trên baseline đã được vá.

Việc tách giúp khi migration major phát sinh lỗi, nhóm có thể so sánh với baseline đã chứa security patch. Nhờ vậy, lỗ hổng không cần được mở lại chỉ để quay về trạng thái trước migration.

## 4. Khi nào không thể hoặc không nên tách hoàn toàn?

Không phải lúc nào cũng có một bản vá độc lập cho nhánh hiện tại. Có thể không tách được khi:

- Nhà cung cấp chỉ sửa lỗ hổng trong major version mới.
- Phiên bản cũ đã hết hỗ trợ và không còn nhận security update.
- Bản vá yêu cầu thay đổi API hoặc cấu trúc dữ liệu mà chỉ major mới hỗ trợ.
- Dependency bị ảnh hưởng là một phần không thể thay thế của framework; nâng riêng nó tạo ra tổ hợp phiên bản không được hỗ trợ.
- Bản vá và migration cần cùng một thay đổi schema/protocol để tránh tạo trạng thái không an toàn.
- Có yêu cầu khẩn cấp buộc triển khai trong một cửa sổ duy nhất.

Trong các trường hợp đó, vẫn nên **tách logic và bằng chứng**, dù không thể tách artifact triển khai. Nhóm có thể chuẩn bị các commit riêng, kiểm thử từng biến thể trên nhánh điều tra, sau đó kết hợp các thay đổi cần thiết thành một release đã được đánh giá.

Không được trì hoãn một bản vá có nguy cơ khai thác nghiêm trọng chỉ để giữ cho quá trình phân tích nguyên nhân thuận tiện. Nếu cần triển khai đồng thời, hãy ưu tiên giảm rủi ro bảo mật, đồng thời tăng cường kiểm thử, quan sát và phương án khôi phục. Nếu bản vá chỉ có trong major mới, việc nâng major có thể chính là hành động khắc phục bắt buộc.

## 5. Thiết kế các nhánh và commit để giữ khả năng truy vết

### 5.1. Bắt đầu từ một baseline xác định

Trước khi chỉnh sửa, xác định commit nền đã được kiểm chứng, tag phát hành, JDK, build tool, dependency lock/BOM và kết quả test. Baseline cần tái tạo được để so sánh.

Ví dụ quy ước nhánh:

```text
main
  ├── security/CVE-2026-12345
  └── migration/java21-framework-major
```

Tên CVE và nhánh chỉ là ví dụ. Dự án có thể dùng quy ước khác, miễn là mỗi nhánh có mục tiêu rõ ràng và liên kết được với issue/advisory.

### 5.2. Nhánh bảo mật chỉ chứa thay đổi cần cho bản vá

Nhánh bảo mật nên chứa dependency update, cấu hình hoặc code change thực sự cần để xử lý lỗ hổng. Tránh đưa formatter, refactor không liên quan, đổi framework major hoặc nâng hàng loạt dependency vào cùng nhánh.

Ví dụ lịch sử commit:

```text
security/CVE-2026-12345
  1. Update vulnerable-client to fixed patch release
  2. Add regression test for vulnerable input
  3. Update security advisory record
```

Mỗi commit nên mô tả nguyên nhân và bằng chứng. Nếu phải thay đổi nhiều module, vẫn cần giữ liên kết tới CVE và lý do từng thay đổi thuộc phạm vi bản vá.

### 5.3. Nhánh major migration có phạm vi riêng

Nhánh migration chứa thay đổi JDK/framework/API cần thiết cho mục tiêu major. Nếu nhánh bảo mật đã được merge hoặc phát hành, hãy tạo migration branch từ baseline đã vá để không vô tình quay về dependency dễ bị khai thác.

Nếu cần phân tích tác động riêng của major migration, tạo một worktree hoặc nhánh thử nghiệm từ commit đã vá rồi áp dụng các thay đổi major. Tránh reset hoặc rewrite nhánh đang được dùng chung; giữ lại commit và artifact để có thể truy vết.

### 5.4. Cherry-pick và merge có kiểm soát

Nếu nhánh bảo mật cần được đưa vào nhiều nhánh release đang được hỗ trợ, có thể cherry-pick commit hoặc merge theo chính sách repository. Sau khi áp dụng, phải chạy lại test trên từng nhánh vì patch có thể phụ thuộc API hoặc dependency khác nhau.

Không nên cherry-pick mù quáng một commit từ major branch về nhánh cũ. Nếu commit đó dùng API mới hoặc thay đổi cấu trúc đã đổi, cần backport riêng và kiểm thử trong đúng môi trường của nhánh đích.

Ví dụ lệnh Git minh họa:

```bash
# Tạo nhánh vá bảo mật từ baseline đã xác định
git switch -c security/CVE-2026-12345 <baseline-tag>

# Sau khi kiểm thử và commit bản vá, chuyển sang nhánh migration
git switch -c migration/java21-framework-major <security-patch-commit>

# Kiểm tra lịch sử và khác biệt của migration
git log --oneline --decorate -n 20
git diff <security-patch-commit>..HEAD
```

Các placeholder như `<baseline-tag>` và `<security-patch-commit>` phải được thay bằng commit/tag thực tế đã xác minh. Không chạy các lệnh trên một cách máy móc nếu repository có quy tắc branch protection hoặc release flow riêng.

## 6. Ma trận kiểm thử để truy tìm nguyên nhân

Để biết bản vá hay migration major gây lỗi, cần tạo các biến thể có thể so sánh từ cùng baseline. Một ma trận tối thiểu gồm:

| Biến thể | Security patch | Major migration | Mục đích |
| --- | --- | --- | --- |
| A — Baseline | Không | Không | Xác nhận trạng thái gốc và kiểm tra môi trường test. |
| B — Patch only | Có | Không | Xác định ảnh hưởng riêng của bản vá bảo mật. |
| C — Major only | Không | Có | Xác định ảnh hưởng riêng của migration major khi có thể kiểm thử an toàn. |
| D — Combined | Có | Có | Xác nhận tổ hợp cuối cùng và phát hiện tương tác giữa hai thay đổi. |

Không phải biến thể C nào cũng được phép chạy hoặc phát hành. Nếu baseline có lỗ hổng nghiêm trọng, chỉ thực hiện trên môi trường cô lập, dữ liệu giả lập và trong thời gian cần thiết để điều tra; không đưa biến thể dễ bị khai thác lên production. Nếu nhà cung cấp không hỗ trợ major mới khi chưa có patch, biến thể C có thể không hợp lệ và phải ghi rõ giới hạn này.

### 6.1. Giữ các điều kiện thử nghiệm giống nhau

Khi so sánh A, B, C và D, giữ cố định những yếu tố không thuộc biến đang kiểm tra:

- Cùng source baseline và cùng tập test, trừ test mới được thêm có chủ đích.
- Cùng JDK/build tool nếu đang đo riêng ảnh hưởng dependency patch; nếu kiểm tra major JDK thì ghi rõ sự thay đổi này.
- Cùng cấu hình, biến môi trường, database snapshot và dữ liệu đầu vào.
- Cùng dependency repository, lockfile/BOM và quy tắc phân giải.
- Cùng loại container/OS/CPU và resource limit khi so sánh runtime.
- Cùng lệnh build/test và tiêu chí pass/fail.

Nếu cần thay đổi nhiều yếu tố cùng lúc, ghi rõ chúng là một biến thể tổng hợp. Không kết luận một dependency là nguyên nhân chỉ dựa trên việc lỗi xuất hiện sau một lần build có nhiều thay đổi.

### 6.2. Diễn giải kết quả

| Kết quả quan sát | Hướng điều tra |
| --- | --- |
| A pass, B fail | Tập trung vào security patch, dependency được thay, cấu hình bảo mật và regression test. |
| A pass, C fail | Tập trung vào thay đổi major: API, framework, JDK, plugin, cấu hình và runtime. |
| B pass, C pass, D fail | Có thể có tương tác giữa patch và major; kiểm tra dependency alignment, thứ tự classpath, cấu hình và contract giữa các thành phần. |
| A fail, B/C/D có kết quả khác nhau | Baseline đã có lỗi hoặc môi trường test không ổn định; phân biệt lỗi có trước và lỗi mới. |
| C không thể tạo hợp lệ vì thiếu patch cần thiết | Ghi nhận giới hạn của ma trận; dùng nhánh thử nghiệm cô lập hoặc so sánh commit/diff khác, không giả định kết quả C. |

Một lần pass/fail không luôn đủ để kết luận. Với test không ổn định, race condition hoặc hiệu năng, cần chạy lặp lại, kiểm soát dữ liệu và xem log/metric. Với lỗi chỉ xuất hiện ở production, thu thập bằng chứng runtime mà không đưa hệ thống vào trạng thái rủi ro không cần thiết.

## 7. Theo dõi dependency và security advisory

### 7.1. Xác định dependency bị ảnh hưởng

Một CVE có thể nằm trong dependency bắc cầu mà nhóm không khai báo trực tiếp. Vì vậy, cần kiểm tra dependency graph theo đúng configuration và artifact được đóng gói.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency vulnerable-artifact --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree -Dscope=runtime
mvn help:effective-pom
```

Kiểm tra cả runtime, compile, test, plugin và buildscript dependency khi chúng có thể ảnh hưởng đến quá trình phát hành. Một lỗ hổng trong build plugin có thể tác động đến pipeline ngay cả khi artifact production không đóng gói plugin đó.

### 7.2. Xác minh fixed version và phạm vi ảnh hưởng

Không chỉ dựa vào một kết quả scanner. Đối chiếu advisory của nhà cung cấp, changelog, metadata của package và phiên bản được resolve thực tế. Ghi nhận:

- Phiên bản bị ảnh hưởng và phiên bản đầu tiên đã sửa.
- Điều kiện khai thác và module/chức năng có sử dụng đường code dễ bị ảnh hưởng không.
- Có bản vá cho nhánh đang dùng hay chỉ có bản phát hành major mới.
- Bản vá có yêu cầu nâng dependency nền, JDK hoặc framework không.
- Có regression/known issue được nhà cung cấp công bố không.

Nếu scanner báo vulnerable version nhưng dependency không được đóng gói hoặc không thể đi tới trong runtime, vẫn cần ghi lại lý do và bằng chứng loại trừ theo policy của tổ chức. Không tự bỏ qua finding chỉ vì chưa thấy đường gọi trong mã nguồn.

### 7.3. Dùng SBOM và scan để kiểm chứng sau thay đổi

Software Bill of Materials (SBOM) giúp ghi nhận các thành phần có trong artifact. Khi đã vá, tạo lại SBOM từ artifact mới và scan lại để xác nhận dependency thực tế đã chuyển sang fixed version. So sánh SBOM trước/sau giúp phát hiện thay đổi ngoài dự kiến trong dependency graph.

Một bản cập nhật có thể sửa CVE đã biết nhưng kéo theo một dependency khác đang có lỗ hổng. Vì vậy, cần kiểm tra tổng thể kết quả sau thay đổi, không chỉ xác nhận một CVE cụ thể đã biến mất.

## 8. Tổ chức commit và báo cáo thay đổi

### 8.1. Tách commit theo mục tiêu

Giữ commit bảo mật độc lập với commit major migration khi có thể. Ví dụ:

```text
SECURITY: Upgrade vulnerable HTTP client to fixed release
TEST: Add regression coverage for CVE-2026-12345
MIGRATION: Move application to Java 21 toolchain
MIGRATION: Upgrade framework major and Jakarta APIs
MIGRATION: Align persistence and test dependencies
```

Commit nhỏ giúp reviewer hiểu từng thay đổi và hỗ trợ `git bisect` khi regression xuất hiện. Nếu cần một commit tổng hợp để phát hành, vẫn giữ lịch sử hoặc liên kết tới các commit thành phần.

### 8.2. Ghi nhận bằng chứng ở từng bước

Với bản vá bảo mật, lưu advisory/CVE, fixed version, dependency path, test hồi quy và kết quả scan sau build. Với major migration, lưu migration guide đã áp dụng, thay đổi API/configuration, JDK/build tool, dependency graph và kết quả test.

Trong pull request hoặc change record, nêu rõ:

- Mục tiêu thay đổi và các issue/advisory liên quan.
- Những dependency hoặc module được thay đổi.
- Những thành phần được giữ nguyên có chủ đích.
- Lệnh build/test và môi trường chạy.
- Kết quả pass/fail, cảnh báo còn tồn tại và giới hạn kiểm thử.
- Kế hoạch rollout, quan sát và rollback.

Không ghi “all tests passed” nếu chỉ chạy unit test. Hãy nêu đúng phạm vi test để người review hiểu bằng chứng đang chứng minh điều gì.

## 9. Truy tìm regression bằng Git và công cụ build

### 9.1. So sánh commit và dependency graph

Khi lỗi xuất hiện, bắt đầu bằng việc xác định thay đổi nào đi vào artifact:

```bash
git diff <known-good-commit>..<failing-commit> -- build.gradle settings.gradle gradle/libs.versions.toml
git diff <known-good-commit>..<failing-commit> -- pom.xml
git log --oneline --decorate <known-good-commit>..<failing-commit>
```

Đối chiếu với dependency graph ở runtime, không chỉ file khai báo. Version catalog, BOM, plugin management, constraint và dependency substitution có thể khiến phiên bản resolve khác với điều người đọc suy luận từ một dòng khai báo.

### 9.2. Dùng `git bisect` khi có thể tạo phép thử tự động

Nếu regression có thể tái hiện bằng một lệnh test hoặc build ổn định, `git bisect` giúp tìm commit đầu tiên làm lỗi xuất hiện:

```bash
git bisect start
git bisect bad <failing-commit>
git bisect good <known-good-commit>
git bisect run ./gradlew test --tests com.example.CompatibilityTest
git bisect reset
```

Ví dụ dùng Gradle; với Maven có thể thay bằng lệnh test phù hợp. Chỉ dùng `git bisect run` khi lệnh trả mã thoát đáng tin cậy: test fail phải trả non-zero, môi trường cần thiết phải có sẵn và kết quả không bị ảnh hưởng bởi test flaky. Nếu không, thực hiện bisect thủ công và ghi lại từng bước.

`git bisect` xác định commit gây thay đổi trạng thái theo phép thử đã định nghĩa. Nó không tự giải thích nguyên nhân kỹ thuật và cũng không phân biệt được hai thay đổi được gộp trong cùng một commit. Vì vậy, commit tách mục tiêu và test hồi quy là điều kiện giúp công cụ hữu ích.

### 9.3. Kiểm tra class loading và runtime thực tế

Khi nghi ngờ dependency/classpath, cần biết JVM đã nạp lớp từ JAR nào. Có thể bật log class loading trong môi trường kiểm thử phù hợp:

```bash
java -Xlog:class+load=info -jar application.jar
```

Log này giúp liên hệ class với nguồn nạp, nhưng có thể rất lớn; chỉ bật trong môi trường điều tra và lọc theo package/class cần thiết. Kết hợp với dependency insight, startup log và cấu hình launcher để xác định runtime classpath thực tế.

## 10. Rollout và rollback khi hai thay đổi có thời hạn khác nhau

### 10.1. Phát hành bản vá bảo mật trước

Nếu patch độc lập và nhánh hiện tại còn được hỗ trợ, có thể phát hành một bản cập nhật nhỏ để giảm rủi ro bảo mật trước khi hoàn thành major migration. Sau khi phát hành, xác nhận:

- Artifact production thực sự chứa fixed version.
- Scanner/SBOM không còn báo phiên bản bị ảnh hưởng trong phạm vi đã xử lý.
- Regression test và luồng nghiệp vụ quan trọng vẫn pass.
- Monitoring không cho thấy lỗi mới về latency, kết nối, authentication hoặc xử lý input.
- Nhánh migration major bắt đầu từ baseline đã vá hoặc nhận patch theo quy trình merge rõ ràng.

### 10.2. Phát hành major migration sau

Khi baseline đã có patch, nhóm tiếp tục migration major với các test và tiêu chí riêng. Nếu major migration gây lỗi, có thể quay về artifact đã vá, giữ trạng thái bảo mật tốt hơn so với quay lại artifact dễ bị khai thác.

Điều này chỉ an toàn nếu schema, message và dữ liệu được tạo bởi phiên bản mới vẫn tương thích với phiên bản đã vá. Nếu migration có thay đổi dữ liệu không thể đọc ngược, cần chiến lược expand–migrate–contract hoặc roll-forward riêng.

### 10.3. Khi buộc phải phát hành cùng lúc

Nếu patch chỉ tồn tại trong major mới hoặc thời hạn bảo mật không cho phép chia đợt, chuẩn bị một release kết hợp. Dù vậy, cần có commit/nhánh và test phân biệt từng phần khi có thể; chạy test tổng hợp trên artifact cuối; ghi rõ các phần không thể thử độc lập và lý do.

Rollback phải cân nhắc bảo mật. Nếu artifact cũ chứa lỗ hổng đang bị khai thác, rollback toàn bộ có thể không phải phương án chấp nhận được. Cần chuẩn bị roll-forward, feature flag, giảm exposure hoặc biện pháp bảo vệ mạng ở mức được phê duyệt.

## 11. Case study: bản vá thư viện HTTP và migration framework major

Giả sử một ứng dụng đang chạy Java 17 và framework thế hệ cũ. Một HTTP client dependency có CVE; nhà cung cấp phát hành fixed patch trong nhánh hiện tại. Cùng thời điểm, nhóm lên kế hoạch chuyển sang Java 21 và framework major mới có namespace Jakarta.

### 11.1. Phương án tách thành hai workstream

**Workstream bảo mật:**

1. Xác định artifact dễ bị ảnh hưởng qua runtime dependency graph.
2. Đối chiếu CVE/advisory và chọn fixed patch được hỗ trợ trên framework hiện tại.
3. Tạo nhánh bảo mật từ tag đang chạy production.
4. Nâng đúng dependency cần vá và thêm regression test cho input/đường khai thác.
5. Build, integration test, tạo SBOM và scan lại artifact.
6. Phát hành bản vá nhỏ và xác nhận runtime đang dùng fixed version.

**Workstream major migration:**

1. Tạo nhánh từ commit đã chứa bản vá bảo mật.
2. Kiểm tra Gradle/Maven wrapper và plugin có hỗ trợ JDK 21.
3. Nâng framework major theo migration guide và chuyển các API Jakarta liên quan.
4. Căn chỉnh persistence, validation, security, HTTP client và test dependencies theo BOM mục tiêu.
5. Chạy unit, integration, contract và runtime test trên image JDK 21.
6. So sánh hiệu năng, startup, lỗi kết nối và hành vi HTTP với baseline đã vá.

### 11.2. Diễn giải khi có lỗi

Giả sử sau khi vá, bản B chạy tốt. Sau khi nâng major trên baseline đã vá, bản D xuất hiện lỗi timeout HTTP.

Nhóm cần so sánh cấu hình timeout, connection pool, TLS, retry policy và phiên bản HTTP client trong dependency graph. Nếu B không có lỗi còn D có lỗi, điều tra tập thay đổi major hoặc tương tác giữa framework và client. Nếu test trên biến thể major-only có thể thực hiện an toàn trong môi trường cô lập, kết quả có thể bổ sung bằng chứng; nếu không, không tạo biến thể thiếu patch để chạy production.

Nếu timeout chỉ xuất hiện khi bật một cấu hình mới của framework, thử nghiệm có kiểm soát bằng cách giữ dependency patch và thay riêng cấu hình đó. Ghi nhận metric kết nối, pool saturation và log handshake để xác định cơ chế. Không vội rollback về artifact dễ bị khai thác nếu có thể giữ bản vá và sửa tiến về phía trước.

### 11.3. Điều kiện hoàn tất

Workstream bảo mật chỉ hoàn tất khi fixed version có mặt trong artifact triển khai, scan/SBOM xác nhận và regression test liên quan pass. Workstream major chỉ hoàn tất khi hệ thống đáp ứng yêu cầu build/runtime/API/data trên nền tảng mới, các lỗi do thay đổi major được xử lý và kế hoạch rollout/rollback đã được xác nhận.

Hai workstream có thể dùng chung một số test hoặc artifact, nhưng kết quả và tiêu chí chấp nhận phải được ghi riêng để không làm mờ trách nhiệm.

## 12. Checklist ra quyết định có tách hay không

Trước khi bắt đầu, nhóm có thể dùng các câu hỏi sau:

- Có fixed version cho nhánh hiện tại không?
- Nhánh hiện tại còn được nhà cung cấp hỗ trợ không?
- Bản vá có kéo theo breaking API hoặc thay đổi framework major không?
- Có thể tạo commit và artifact độc lập cho security patch không?
- Có thể chạy test patch-only mà không tạo rủi ro bảo mật không?
- Migration major có đủ lớn để cần điều tra riêng khi regression xuất hiện không?
- Có cần giữ consumer hoặc runtime cũ trong thời gian chuyển tiếp không?
- Nếu phải kết hợp, có thể kiểm thử riêng các commit/biến thể trong môi trường cô lập không?
- Rollback có làm hệ thống quay về phiên bản dễ bị khai thác không?
- Có SBOM, scan, regression test và log/metric để xác nhận kết quả không?

Nếu câu trả lời cho các câu hỏi về fixed version, hỗ trợ và tính độc lập đều là có, tách patch và major thường đem lại khả năng truy vết tốt hơn. Nếu không, ghi rõ ràng buộc khiến việc tách không khả thi và tăng cường bằng chứng cho release kết hợp.

## 13. Kết luận

Tách bản vá bảo mật khỏi thay đổi major là một kỹ thuật kiểm soát biến số trong migration. Nó giúp nhóm xác định tác động của bản vá, đánh giá migration độc lập, khoanh vùng regression và giữ đường rollback có mức bảo mật phù hợp. Việc tách nên được thực hiện khi có bản vá độc lập được hỗ trợ và không tạo ra tổ hợp dependency ngoài ma trận tương thích.

Khi không thể tách artifact hoặc thời hạn bảo mật yêu cầu phát hành cùng lúc, nhóm vẫn cần tách commit, test, bằng chứng và tiêu chí chấp nhận theo từng mục tiêu. Không trì hoãn xử lý lỗ hổng nghiêm trọng chỉ để thuận tiện điều tra; thay vào đó, dùng baseline rõ ràng, ma trận kiểm thử, SBOM, dependency analysis và quan sát runtime để tìm nguyên nhân mà vẫn kiểm soát được rủi ro.
