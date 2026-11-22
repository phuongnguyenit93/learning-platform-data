# Dùng OpenRewrite hoặc công cụ IDE cho thay đổi có thể tự động hóa

Trong một cuộc Java migration, nhiều thay đổi lặp lại trên hàng trăm file: đổi package hoặc kiểu dữ liệu, thay API đã deprecated, cập nhật cấu hình build, sửa import, điều chỉnh annotation hoặc chuyển đổi cú pháp theo phiên bản Java mới. Sửa thủ công từng nơi dễ bỏ sót; thay thế chuỗi bằng regex có thể làm hỏng code ở những vị trí không cùng ý nghĩa. Các công cụ refactoring trong IDE và OpenRewrite giúp tự động hóa những thay đổi có quy luật, đồng thời cung cấp cách xem trước và kiểm soát phạm vi.

**OpenRewrite** là framework tự động chuyển đổi source code và một số loại cấu hình bằng các recipe có thể kết hợp, tái sử dụng và chạy lặp lại. **Công cụ refactoring của IDE** phân tích cấu trúc project để thực hiện những thao tác như rename, move, change signature hoặc tìm và thay thế theo cấu trúc. Cả hai có thể giảm công việc lặp lại, nhưng kết quả vẫn cần được review và kiểm chứng trên build, test và hành vi ứng dụng.

Chọn công cụ theo bản chất thay đổi: thao tác cục bộ, có hiểu biết về symbol và project thường phù hợp với refactoring IDE; thay đổi có quy tắc áp dụng trên nhiều module hoặc repository thường phù hợp với recipe tự động hóa có thể chạy lại. Những thay đổi cần quyết định nghiệp vụ, xử lý dữ liệu hoặc thiết kế lại kiến trúc vẫn cần người phát triển xác định semantics trước khi tự động sửa code.

## 1. Nhận diện thay đổi có thể tự động hóa

Một thay đổi phù hợp để tự động hóa thường có các đặc điểm:

- Có quy tắc xác định được từ cấu trúc code, tên symbol, kiểu dữ liệu, annotation hoặc cấu hình.
- Có thể xác định rõ file, module và phiên bản chịu ảnh hưởng.
- Có kết quả mong đợi đủ rõ để kiểm tra trước và sau.
- Có thể áp dụng nhất quán trên nhiều vị trí mà không cần quyết định riêng cho từng nghiệp vụ.
- Có cách kiểm tra tự động như compile, test, contract test hoặc diff.

Ví dụ phù hợp gồm đổi một type cũ sang type mới, đổi tên method theo API mới, thêm import, loại import thừa, cập nhật version dependency, chuyển cú pháp Java theo recipe đã xác định, hoặc sửa key trong file properties/YAML theo quy tắc rõ ràng.

Những trường hợp sau cần thận trọng hơn:

- Cùng một tên method nhưng semantics khác nhau tùy overload hoặc kiểu receiver.
- Thay đổi cách xử lý `null`, exception, transaction, retry hoặc thứ tự side effect.
- Đổi API yêu cầu chuyển đổi dữ liệu, cấu hình hoặc hành vi nghiệp vụ.
- Chuyển đồng thời nhiều module có dependency và thứ tự nâng cấp khác nhau.
- Thay đổi chỉ đúng khi biết ngữ cảnh runtime, cấu hình triển khai hoặc consumer bên ngoài.

Một recipe có thể thay được tên API, nhưng không thể tự suy ra chính sách retry mới nên là bao nhiêu lần, giao dịch nào phải rollback hoặc dữ liệu lịch sử cần chuyển đổi thế nào nếu các quyết định đó chưa được mô tả.

## 2. OpenRewrite hoạt động như thế nào?

OpenRewrite thực hiện thay đổi thông qua **recipe**. Recipe mô tả một phép chuyển đổi cụ thể hoặc kết hợp nhiều phép chuyển đổi nhỏ. Recipe có thể được viết bằng YAML để cấu hình và kết hợp các recipe có sẵn, hoặc được triển khai bằng Java khi cần logic phân tích/chuyển đổi riêng.

Thay vì chỉ tìm chuỗi ký tự, OpenRewrite phân tích source thành cấu trúc cú pháp và thông tin kiểu khi có thể. Với Java, framework sử dụng mô hình cây cú pháp có khả năng giữ lại định dạng và trivia của source, thường được gọi là Lossless Semantic Tree (LST). Nhờ đó recipe có thể nhắm tới type, method invocation, annotation hoặc cấu trúc cụ thể mà không phải thay mọi chuỗi trùng tên trong file.

Quy trình khái quát:

```text
Source code / build files / configuration
                  |
                  v
        Parse và xây dựng mô hình
                  |
                  v
        Áp dụng recipe đã chọn
                  |
                  v
       Tạo thay đổi trên mô hình
                  |
          +-------+-------+
          |               |
          v               v
       Dry run          Run
          |               |
          v               v
      Xem diff       Ghi source đã sửa
          |               |
          +-------+-------+
                  |
                  v
        Review, compile và test
```

Mô hình cú pháp và type attribution giúp recipe hiểu code tốt hơn regex, nhưng chất lượng kết quả vẫn phụ thuộc vào parser, classpath, recipe và độ đầy đủ của thông tin project. Khi type attribution thiếu hoặc dependency không được phân giải, một recipe dựa trên type có thể không nhận diện được tất cả vị trí cần đổi.

### 2.1. Recipe đơn và recipe tổng hợp

Một recipe đơn thường thực hiện một thay đổi có phạm vi rõ. Recipe tổng hợp (composite recipe) kết hợp nhiều recipe theo một mục tiêu migration, ví dụ thay type, cập nhật import và chỉnh cấu hình liên quan.

Một recipe thường có:

- Tên định danh duy nhất, thường là fully qualified name.
- Mô tả mục đích và phạm vi thay đổi.
- Các tham số cấu hình nếu recipe cần biết tên type, version hoặc giá trị cũ/mới.
- Danh sách recipe con nếu là composite.
- Logic xác định node nào cần xử lý và thay đổi như thế nào.

Recipe có thể có tiền điều kiện, chỉ chạy khi project, file hoặc type đáp ứng điều kiện cụ thể. Việc giới hạn phạm vi giúp tránh thay đổi nhầm code không thuộc migration.

### 2.2. Ví dụ recipe YAML

Giả sử một thư viện đổi type `com.legacy.client.JsonClient` thành `com.modern.client.JsonClient`. Có thể định nghĩa một recipe tổng hợp như sau:

```yaml
type: specs.openrewrite.org/v1beta/recipe
name: com.example.migration.ReplaceLegacyJsonClient
displayName: Replace legacy JSON client type
description: Replace the legacy client type and clean obsolete imports.
recipeList:
  - org.openrewrite.java.ChangeType:
      oldFullyQualifiedTypeName: com.legacy.client.JsonClient
      newFullyQualifiedTypeName: com.modern.client.JsonClient
  - org.openrewrite.java.RemoveUnusedImports
```

Đây là ví dụ cấu trúc recipe; recipe cần được đặt ở vị trí cấu hình mà build plugin nhận diện và các recipe được tham chiếu phải có trong dependency recipe tương ứng. Tên recipe, tham số và artifact chứa recipe phải được xác nhận theo phiên bản OpenRewrite được pin trong project.

Recipe `ChangeType` nhắm tới kiểu Java theo fully qualified name. Nó có thể cập nhật các vị trí tham chiếu kiểu mà parser nhận diện được, thay vì thay mọi chuỗi `JsonClient` trong source. Recipe dọn import xử lý các import không còn cần thiết sau chuyển đổi.

Tuy nhiên, đổi type không tự động bảo đảm thư viện mới có cùng method, constructor, exception hoặc semantics. Nếu API mới khác, cần recipe bổ sung cho các thay đổi cú pháp đã hiểu rõ và cập nhật thủ công những phần cần quyết định hành vi.

### 2.3. Recipe Java tùy chỉnh

Khi recipe có sẵn không đáp ứng được quy tắc, có thể viết recipe bằng Java. Recipe tùy chỉnh thường dùng visitor để duyệt các node của LST, kiểm tra loại node và thông tin kiểu, sau đó trả về node đã chỉnh sửa. Ví dụ, một recipe nội bộ có thể chỉ đổi lời gọi method trên một type xác định, đồng thời kiểm tra số lượng tham số hoặc kiểu trả về.

Một recipe tốt nên:

- Chỉ sửa node nằm trong phạm vi được mô tả.
- Không phụ thuộc vào vị trí dòng hoặc khoảng trắng nếu không cần thiết.
- Có kiểm tra type/symbol khi quy tắc phụ thuộc ngữ nghĩa.
- Giữ nguyên comment, định dạng và phần code không liên quan.
- Có test cho trường hợp được sửa, trường hợp không được sửa và các biến thể cú pháp.
- Có tính idempotent: chạy lại không tiếp tục tạo diff mới khi code đã đạt trạng thái đích.

Không nên viết recipe tùy chỉnh chỉ để thay chuỗi đơn giản nếu một recipe có sẵn hoặc refactoring IDE đã giải quyết đúng vấn đề. Mã recipe cũng cần được bảo trì và kiểm thử như mã sản phẩm.

## 3. Tích hợp OpenRewrite với Gradle

OpenRewrite có Gradle plugin để khám phá và chạy recipe trong project. Cấu hình cụ thể phụ thuộc phiên bản plugin, recipe artifact và Gradle đang dùng; nên pin các phiên bản thay vì dựa vào `latest.release` trong pipeline.

Ví dụ cấu hình Groovy DSL:

```groovy
plugins {
    id 'org.openrewrite.rewrite' version '<rewrite-plugin-version>'
}

repositories {
    mavenCentral()
}

dependencies {
    rewrite 'org.openrewrite.recipe:rewrite-migrate-java:<recipe-version>'
}

rewrite {
    activeRecipe 'org.openrewrite.java.migrate.UpgradeToJava17'
}
```

Các chuỗi `<rewrite-plugin-version>` và `<recipe-version>` là placeholder; cần thay bằng phiên bản đã được kiểm tra và pin trong repository. Tên recipe minh họa phải tồn tại trong recipe artifact đã khai báo. Với project thực tế, kiểm tra catalog/recipe discovery của đúng dependency trước khi kích hoạt.

Các lệnh thường dùng:

```bash
./gradlew rewriteDiscover
./gradlew rewriteDryRun
./gradlew rewriteRun
```

- `rewriteDiscover` hỗ trợ tìm recipe có thể sử dụng trong cấu hình hiện tại.
- `rewriteDryRun` tạo báo cáo/diff dự kiến để review mà không áp dụng thay đổi vào source theo mục đích dry run.
- `rewriteRun` thực thi recipe và ghi thay đổi vào source.

Tên task và cách cấu hình chi tiết cần đối chiếu với phiên bản plugin đã chọn. Trong multi-project build, cần xác định task áp dụng ở root, subproject hay một tập module cụ thể; không chạy recipe toàn repository nếu mục tiêu chỉ là một module.

### 3.1. Chọn đúng phạm vi Gradle

Trong Gradle multi-project, một recipe có thể được áp dụng cho nhiều subproject. Trước khi chạy, xác định:

- Recipe được kích hoạt ở root hay từng subproject.
- Những project nào có source set cần chuyển đổi.
- Build logic, convention plugin hoặc generated source có nằm trong phạm vi hay không.
- Test source và integration test có cần thay đổi tương ứng không.
- File generated hoặc vendored có được phép chỉnh sửa không.

Nếu project dùng Java toolchain, cần giữ cấu hình compiler/runtime toolchain nhất quán với migration. OpenRewrite không tự thay thế việc kiểm tra toolchain của Gradle và không chứng minh ứng dụng chạy trên JDK đích.

## 4. Tích hợp OpenRewrite với Maven

Với Maven, có thể cấu hình `rewrite-maven-plugin` cùng recipe artifact. Ví dụ minh họa:

```xml
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>${rewrite.maven.plugin.version}</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.migrate.UpgradeToJava17</recipe>
        </activeRecipes>
        <recipeArtifactCoordinates>
            <recipeArtifactCoordinate>
                org.openrewrite.recipe:rewrite-migrate-java:${rewrite.recipe.version}
            </recipeArtifactCoordinate>
        </recipeArtifactCoordinates>
    </configuration>
</plugin>
```

Các property version phải được định nghĩa và pin trong project. Recipe cần có trong artifact được nạp; xác minh tên recipe với phiên bản cụ thể trước khi chạy.

Các goal thường dùng:

```bash
mvn rewrite:discover
mvn rewrite:dryRun
mvn rewrite:run
```

Dry run giúp tạo diff để review trước khi thay đổi source. Sau khi review và chấp nhận, `rewrite:run` áp dụng recipe. Với Maven multi-module, hãy xác định reactor/module được chọn, profile đang hoạt động và cách plugin được kế thừa để không sửa ngoài phạm vi.

## 5. Chọn và sử dụng recipe migration

OpenRewrite có nhiều recipe cho Java, thư viện, framework và cấu hình build. Recipe thường được nhóm theo mục tiêu như nâng cấp Java, chuyển đổi API, cập nhật Spring, thay đổi dependency hoặc chuẩn hóa cấu hình Maven/Gradle.

Khi chọn recipe, kiểm tra:

1. **Tên và phiên bản:** recipe có tồn tại trong artifact/version đang pin không?
2. **Mục tiêu:** recipe nâng cấp tới release nào, thư viện nào và phạm vi nào?
3. **Điều kiện:** recipe yêu cầu source level, dependency hoặc classpath cụ thể nào?
4. **Thay đổi đi kèm:** recipe có chỉnh build file, import, annotation, cấu hình hay test không?
5. **Giới hạn:** recipe có phần nào cần xử lý thủ công hoặc không hỗ trợ framework đang dùng?
6. **Báo cáo:** recipe có tạo data table hoặc output giúp biết file và symbol nào đã thay đổi không?

Không chọn recipe chỉ dựa vào tên gần giống mục tiêu. Hãy xem mô tả, source, changelog và test của recipe nếu migration có ảnh hưởng rộng. Một recipe tổng hợp có thể bao gồm nhiều bước; cần biết nó thay đổi những gì trước khi chạy.

### 5.1. Khám phá recipe trước khi kích hoạt

Sử dụng task discovery của plugin để liệt kê recipe có thể dùng. Sau đó xác định fully qualified recipe name, đọc tài liệu tương ứng và thử trên một module hoặc nhánh kiểm thử nhỏ.

Nếu recipe không được tìm thấy, kiểm tra recipe artifact đã được khai báo trong đúng configuration chưa, repository Maven có truy cập được không, và tên recipe có thay đổi giữa các phiên bản không. Không thay tên recipe bằng phỏng đoán.

### 5.2. Tách migration lớn thành các nhóm nhỏ

Ví dụ, nâng cấp từ một framework cũ lên framework mới có thể gồm:

- Cập nhật dependency và plugin version.
- Chuyển package hoặc API.
- Thay annotation hoặc method đã thay đổi.
- Cập nhật file cấu hình YAML/properties.
- Thay test, mock hoặc test fixture.
- Sửa code cần quyết định semantics hoặc xử lý thủ công.

Không nhất thiết chạy tất cả trong một lần. Chia thành các recipe có mục tiêu rõ giúp review diff và khoanh vùng lỗi dễ hơn. Mỗi nhóm nên có build/test phù hợp trước khi tiếp tục nhóm kế tiếp.

## 6. Dùng công cụ refactoring trong IDE

IDE hiện đại có mô hình cú pháp, symbol index, type resolution và project model. Vì vậy, refactoring tích hợp trong IDE thường an toàn hơn tìm/thay chuỗi thuần văn bản khi thay đổi liên quan đến class, method, package hoặc quan hệ tham chiếu.

Các IDE phổ biến như IntelliJ IDEA và Eclipse cung cấp nhiều refactoring; VS Code có các thao tác phụ thuộc Java extension và language server đã cài. Tên menu và mức hỗ trợ có thể khác theo phiên bản IDE.

### 6.1. Các refactoring thường dùng

| Thao tác | Mục đích | Điểm cần review |
|---|---|---|
| Rename | Đổi tên class, method, field, package hoặc biến | Tác động đến reflection, string-based configuration, JSON/JPA name hoặc public API |
| Change Signature | Thêm/xóa/đổi tham số hoặc kiểu trả về | Consumer, overload, constructor, method reference và binary compatibility |
| Move | Chuyển class/package | Package visibility, import, module boundary, resource path và scan configuration |
| Extract Method | Tách đoạn code thành method | Biến capture, exception, thứ tự side effect và visibility |
| Inline | Đưa nội dung method/variable vào nơi sử dụng | Đánh giá số lượng call site và khả năng đọc |
| Safe Delete | Xóa symbol và các tham chiếu được IDE nhận diện | Reflection, dependency bên ngoài và cấu hình dạng chuỗi có thể không được nhận diện |
| Encapsulate Field | Tạo accessor và thay truy cập trực tiếp | Framework binding, serialization, JPA và public field contract |
| Organize Imports | Sắp xếp và loại import thừa | Static import, wildcard và quy ước formatter |

Các refactoring này có thể cập nhật hàng loạt reference trong project, nhưng không bảo đảm phát hiện mọi tham chiếu ngoài source được index. Ví dụ, class name được ghi trong `application.yml`, XML, script, database hoặc plugin registry có thể không được IDE Rename cập nhật.

### 6.2. Dùng Preview và kiểm tra phạm vi

Khi IDE cung cấp preview, hãy xem danh sách file và từng thay đổi trước khi xác nhận. Kiểm tra scope có phải project hiện tại, module hiện tại hay toàn bộ workspace. Với thư viện public, rename hoặc change signature có thể phá source/binary compatibility của consumer bên ngoài workspace.

Các thao tác như Safe Delete thường dựa trên reference mà IDE phân tích được. Chúng không chứng minh symbol không được gọi bằng reflection, service loader, dependency injection, tên trong cấu hình hoặc hệ thống khác. Với API public, cần tìm consumer ngoài repository và xem xét versioning/deprecation.

### 6.3. Structural Search and Replace

Một số IDE hỗ trợ tìm kiếm và thay thế theo cấu trúc (Structural Search and Replace). Cách này dùng pattern cú pháp và placeholder thay vì so khớp chuỗi bất kỳ. Nó phù hợp với thay đổi lặp lại trên một cấu trúc code xác định, ví dụ chuyển một dạng method call sang dạng khác.

Trước khi Replace All, hãy thử pattern trên vài kết quả, kiểm tra placeholder và điều kiện lọc, rồi dùng preview. Pattern quá rộng có thể khớp overload hoặc biểu thức không cùng semantics. Structural search không thay thế hoàn toàn type-aware recipe nếu phép chuyển đổi cần phân biệt type, inheritance hoặc API của dependency.

## 7. So sánh OpenRewrite, IDE refactoring và regex

| Tiêu chí | OpenRewrite | IDE refactoring | Regex/search-replace |
|---|---|---|---|
| Cách hiểu code | Parser/LST, type attribution tùy recipe | Syntax tree, symbol index và project model | Văn bản/ký tự |
| Phạm vi | Có thể chạy lặp lại trên nhiều module/repository | Thường theo workspace/project đang mở | Theo file hoặc tập file được tìm kiếm |
| Tái sử dụng | Recipe có thể version hóa và chạy trong CI | Thường là thao tác tương tác; một số IDE lưu structural template | Pattern có thể lưu nhưng ít hiểu semantics |
| Review | Dry run/diff và báo cáo | Refactoring preview | Danh sách kết quả và diff |
| Phù hợp | Migration có quy tắc, diện rộng, cần lặp lại | Thay đổi có ngữ cảnh trong project và thao tác refactor quen thuộc | Sửa văn bản đơn giản, có ranh giới rõ |
| Rủi ro chính | Recipe/classpath/attribution không đủ hoặc recipe không bao phủ ngoại lệ | Index không thấy consumer ngoài workspace hoặc string-based reference | Sửa nhầm comment, string literal, overload hoặc cú pháp khác |

Không có một công cụ phù hợp cho mọi thay đổi. Có thể dùng OpenRewrite cho đợt chuyển đổi hàng loạt, IDE để xử lý ngoại lệ hoặc thay đổi có tương tác, và regex cho chỉnh sửa văn bản thuần có phạm vi nhỏ. Điều quan trọng là lựa chọn dựa trên semantics và phạm vi, không chỉ dựa trên tốc độ thao tác.

## 8. Quy trình tự động hóa an toàn trong migration

### Bước 1: Xác định quy tắc chuyển đổi

Mô tả chính xác trạng thái trước và sau. Nêu rõ symbol, type, annotation, cấu hình hoặc file nào thuộc phạm vi. Xác định trường hợp ngoại lệ và những thay đổi cần người quyết định.

Ví dụ: “Thay type `com.legacy.client.JsonClient` bằng `com.modern.client.JsonClient` trong source Java của module orders; cập nhật import; giữ nguyên method call; không sửa generated source và không đổi cấu hình production trong bước này.” Mô tả cụ thể như vậy giúp recipe và phạm vi review rõ ràng.

### Bước 2: Chọn công cụ và xác nhận khả năng

Chọn recipe OpenRewrite nếu có recipe đã được kiểm chứng; chọn IDE refactoring nếu thao tác gắn với symbol và phạm vi project hiện tại; chọn structural search nếu pattern cú pháp đủ rõ. Chỉ dùng regex cho thay đổi văn bản mà không cần hiểu cú pháp Java.

Trước khi chạy diện rộng, kiểm tra parser, classpath, phiên bản JDK, build plugin và recipe dependency. Với code nhiều module, bảo đảm công cụ có đủ thông tin để phân giải type.

### Bước 3: Tạo điểm khôi phục và giới hạn scope

Bắt đầu từ working tree có thể review và xác định rõ các thay đổi sẵn có. Dùng branch hoặc commit riêng cho migration; không ghi đè thay đổi chưa thuộc task. Loại trừ generated source, vendor code, output build và file không thuộc quyền sở hữu nếu recipe chưa được thiết kế để sửa chúng.

Chạy trước trên một module hoặc tập file đại diện để xác nhận recipe đúng với cấu trúc thực tế. Nếu diff cho thấy thay đổi ngoài dự kiến, dừng và sửa quy tắc trước khi mở rộng phạm vi.

### Bước 4: Dry run và review diff

Với OpenRewrite, dùng `rewriteDryRun` hoặc `rewrite:dryRun` tùy build tool. Với IDE, bật refactoring preview. Với structural search, xem toàn bộ match và thử một vài trường hợp.

Review các điểm:

- File nào bị sửa và vì sao?
- Có bỏ sót module hoặc source set nào không?
- Có sửa comment, string literal, generated code hoặc test fixture ngoài ý muốn không?
- Import, package, generic type và overload có được chuyển đúng không?
- Recipe có thêm/xóa dependency hoặc chỉnh build file ngoài phạm vi dự kiến không?
- Có thay đổi semantics cần người quyết định không?

Dry run chỉ chứng minh công cụ dự kiến tạo diff; nó không chứng minh diff đúng về nghiệp vụ hoặc tương thích runtime.

### Bước 5: Áp dụng theo nhóm nhỏ

Sau khi review, chạy recipe hoặc refactoring trên phạm vi đã duyệt. Chia thay đổi theo nhóm có thể kiểm chứng: source Java, build file, cấu hình, test hoặc tài liệu. Nhóm nào có rủi ro cao nên có diff và commit riêng để dễ truy vết.

### Bước 6: Build, test và kiểm tra hành vi

Chạy compile, unit test, integration test và contract test phù hợp. Với migration API, kiểm tra cả các trường hợp lỗi, null, ordering, side effect và cấu hình runtime. Nếu đổi dependency, xác minh artifact thực tế được resolve và class nào được nạp.

Tự động hóa source không thay thế kiểm tra dependency và runtime. Recipe có thể sửa code gọi API nhưng không đảm bảo thư viện đích tồn tại trong môi trường triển khai hoặc có semantics tương đương.

### Bước 7: Chạy lại để kiểm tra tính ổn định

Một recipe chuyển đổi trạng thái A sang trạng thái B nên không tiếp tục thay đổi code khi chạy lần hai trên trạng thái B. Chạy dry run lại sau khi đã áp dụng; diff rỗng hoặc chỉ còn các thay đổi được giải thích là tín hiệu tốt về tính idempotent.

Nếu chạy lần hai tiếp tục tạo diff, cần tìm nguyên nhân: recipe chưa idempotent, recipe con phụ thuộc thứ tự, formatter thay đổi lặp lại hoặc trạng thái project chưa ổn định. Không đưa một automation tạo diff liên tục vào pipeline.

### Bước 8: Ghi nhận kết quả và ngoại lệ

Lưu phiên bản plugin, recipe artifact, recipe name, command, phạm vi module, diff và kết quả build/test. Liệt kê các vị trí recipe không xử lý được cùng lý do để developer xử lý thủ công. Báo cáo cần cho biết file nào được tự động sửa và file nào còn chờ quyết định.

## 9. Kiểm thử recipe và refactoring tự động

Recipe tùy chỉnh nên có test riêng. Test thường cung cấp source đầu vào, recipe cần chạy và source đầu ra mong đợi. Cần có cả trường hợp match và không match để xác nhận phạm vi.

Một bộ test cho recipe thay type nên bao gồm:

- Import và khai báo biến dùng type cũ được chuyển sang type mới.
- Type cũ xuất hiện trong generic, field, parameter, return type hoặc annotation được xử lý theo yêu cầu.
- Một class khác có tên đơn giản giống nhau nhưng package khác không bị sửa.
- Comment và string literal chứa tên cũ không bị thay đổi nếu recipe chỉ nhắm tới type.
- Code không có đủ type attribution được xử lý theo chính sách đã định, không âm thầm bỏ qua mà không có báo cáo.
- Chạy recipe lần hai không tạo thêm thay đổi.

Với refactoring IDE, không phải lúc nào cũng có test recipe tự động. Có thể kiểm chứng bằng compile/test, diff và một tập consumer đại diện. Nếu thao tác được lặp lại thường xuyên, cân nhắc chuyển quy tắc ổn định thành recipe có thể version hóa và kiểm thử trong CI.

## 10. Những lỗi thường gặp khi tự động hóa migration

- **Dùng regex cho thay đổi ngữ nghĩa:** cùng một chuỗi có thể xuất hiện trong code, comment, log message, JSON key hoặc tài liệu; thay toàn bộ có thể làm hỏng contract.
- **Tin rằng recipe đã sửa hết:** parser, classpath, type attribution và điều kiện recipe có thể khiến một số trường hợp không được nhận diện.
- **Không pin phiên bản recipe/plugin:** cùng tên recipe ở version khác có thể có logic hoặc dependency khác; kết quả migration khó tái lập.
- **Chạy toàn repository quá sớm:** diff lớn làm khó review và có thể chạm generated/vendor code.
- **Chỉ xem diff mà không build:** code có thể được sửa cú pháp nhưng không compile do dependency hoặc API không khớp.
- **Chỉ compile mà không test:** hành vi, thứ tự, exception hoặc side effect có thể đã thay đổi.
- **Bỏ qua cấu hình và dữ liệu:** source migration có thể cần cập nhật build file, YAML, properties, schema hoặc dữ liệu triển khai.
- **Không kiểm tra lần chạy thứ hai:** recipe không idempotent có thể làm source tiếp tục biến đổi mỗi lần chạy.
- **Dùng Safe Delete/rename mà quên reflection:** string-based reference, framework scanning và consumer ngoài workspace có thể không được IDE nhận diện.
- **Không ghi ngoại lệ:** các vị trí không tự động hóa được dễ bị quên nếu không có báo cáo và owner rõ ràng.

## 11. Checklist trước khi chấp nhận thay đổi tự động

- [ ] Quy tắc chuyển đổi và phạm vi module/file đã được mô tả rõ.
- [ ] Công cụ, plugin, recipe và version đã được pin.
- [ ] Parser/classpath đủ để phân tích các type liên quan.
- [ ] Dry run hoặc preview đã được review.
- [ ] Diff không sửa nhầm comment, string, generated code hoặc file ngoài scope.
- [ ] Những trường hợp recipe không bao phủ đã được liệt kê.
- [ ] Thay đổi source, dependency và cấu hình đã được xử lý đầy đủ.
- [ ] Build, test và kiểm tra hành vi phù hợp đã chạy thành công.
- [ ] Chạy lại recipe không tạo diff ngoài dự kiến.
- [ ] Phiên bản tool, command, diff và bằng chứng kiểm thử được lưu để tái lập.

## 12. Kết luận

OpenRewrite và refactoring IDE giúp chuyển đổi source code theo cấu trúc và giảm các thao tác lặp lại trong Java migration. OpenRewrite phù hợp với recipe có thể version hóa và chạy trên nhiều module; IDE refactoring phù hợp với thay đổi tương tác dựa trên symbol và project model; regex chỉ nên dùng cho thay đổi văn bản có ranh giới rõ. Hãy mô tả quy tắc trước, giới hạn phạm vi, review dry run, áp dụng theo nhóm nhỏ, rồi build/test và kiểm tra tính idempotent. Tự động hóa chỉ hoàn tất khi diff được hiểu rõ và ứng dụng vẫn đáp ứng hợp đồng sau migration.
