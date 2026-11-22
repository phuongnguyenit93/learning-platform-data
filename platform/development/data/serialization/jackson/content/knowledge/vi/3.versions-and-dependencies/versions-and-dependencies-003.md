# Giữ phiên bản các thành phần Jackson tương thích với nhau

Jackson thường được dùng như một nhóm thư viện: thư viện đọc và ghi JSON, thư viện ánh xạ dữ liệu sang kiểu Java, annotation, cùng các module hỗ trợ ngày giờ, Kotlin, YAML hoặc những định dạng khác. Các thành phần này phối hợp với nhau trong cùng một luồng xử lý. Vì vậy, chọn đúng phiên bản cho từng dependency riêng lẻ chưa đủ; ứng dụng cần một tập phiên bản tương thích.

Nếu các module Jackson bị lệch phiên bản, code có thể biên dịch thành công nhưng lỗi khi chạy. Những lỗi như `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi liên kết class thường xuất hiện khi một module gọi API mà phiên bản module khác trên runtime classpath không cung cấp.

Cách quản lý ổn định là xác định một nguồn quản lý phiên bản, dùng Jackson BOM hoặc BOM của framework đang sử dụng, rồi kiểm tra dependency graph thực tế mà Gradle đã chọn.

## 1. Jackson gồm nhiều thành phần có quan hệ với nhau

Một ứng dụng không nhất thiết phải khai báo tất cả thư viện Jackson. Starter hoặc thư viện cấp cao có thể kéo chúng vào dưới dạng dependency bắc cầu. Tuy nhiên, hiểu vai trò của từng thành phần giúp đọc dependency graph và xử lý xung đột chính xác hơn.

| Thành phần | Vai trò |
|---|---|
| `jackson-core` | Streaming API: đọc token JSON và ghi nội dung JSON. |
| `jackson-annotations` | Các annotation như `@JsonProperty`, `@JsonIgnore`, `@JsonCreator`. |
| `jackson-databind` | Ánh xạ giữa JSON và object Java, cung cấp `ObjectMapper`. |
| `jackson-datatype-jsr310` | Hỗ trợ các kiểu ngày giờ trong `java.time`, chẳng hạn `Instant`, `LocalDate`. |
| `jackson-datatype-jdk8` | Hỗ trợ một số kiểu Java 8 như `Optional`. |
| `jackson-module-parameter-names` | Hỗ trợ suy ra tên tham số constructor trong các tình huống phù hợp. |
| `jackson-module-kotlin` | Bổ sung hỗ trợ cho các kiểu và quy ước của Kotlin. |
| `jackson-dataformat-yaml` | Đọc và ghi YAML thông qua hệ sinh thái Jackson. |
| `jackson-dataformat-xml` | Đọc và ghi XML. |

Ba thành phần nền tảng thường gặp là `jackson-core`, `jackson-annotations` và `jackson-databind`. `jackson-databind` phụ thuộc vào hai thành phần nền tảng còn lại. Các module mở rộng cũng có thể gọi API của core hoặc databind.

Ví dụ, khi ứng dụng dùng `JavaTimeModule`, dependency tương ứng là `jackson-datatype-jsr310`. Module này phải tương thích với phiên bản Jackson nền tảng mà ứng dụng đang dùng. Chỉ thêm module ngày giờ vào classpath không đảm bảo nó hoạt động nếu các thành phần Jackson khác đang thuộc một tập phiên bản không tương thích.

Một điểm cần phân biệt: các thư viện có liên quan về chức năng không nhất thiết đều thuộc cùng một nhóm phiên bản. Jackson BOM là nơi công bố các ràng buộc phiên bản đã được phối hợp cho một bản phát hành. Hãy để BOM quyết định phiên bản từng artifact thay vì tự suy ra rằng mọi artifact phải có cùng chuỗi phiên bản.

## 2. Vì sao lệch phiên bản có thể chỉ lỗi lúc chạy?

Gradle giải quyết phiên bản theo từng module tọa độ `group:name`. Chẳng hạn, `jackson-databind` và `jackson-core` là hai module khác nhau. Nếu các dependency khai báo yêu cầu những phiên bản khác nhau, Gradle có thể chọn một phiên bản cho từng module nhưng không tự bảo đảm rằng các module Jackson riêng rẽ đã tạo thành một bộ tương thích.

Ví dụ minh họa một runtime classpath không đồng bộ:

~~~text
com.fasterxml.jackson.core:jackson-databind:2.17.x
com.fasterxml.jackson.core:jackson-core:2.15.x
com.fasterxml.jackson.core:jackson-annotations:2.16.x
com.fasterxml.jackson.datatype:jackson-datatype-jsr310:2.16.x
~~~

Các số phiên bản trên chỉ minh họa tình trạng lệch phiên bản, không phải một cấu hình được khuyến nghị.

Một dependency có thể kéo vào phiên bản cũ của `jackson-core`; dependency khác có thể yêu cầu phiên bản mới hơn của `jackson-databind`. Vì hai artifact có tọa độ khác nhau, việc Gradle chọn được một phiên bản cho mỗi artifact không đồng nghĩa chúng tương thích với nhau.

Có ba thời điểm cần quan tâm:

- **Compile classpath** quyết định các kiểu và API mà compiler nhìn thấy.
- **Runtime classpath** quyết định class thực sự được nạp khi ứng dụng chạy.
- **Dependency graph** giải thích dependency trực tiếp và dependency bắc cầu nào đã yêu cầu từng phiên bản.

Nếu compile classpath và runtime classpath khác nhau, hoặc các module Jackson trên runtime classpath không đồng bộ, ứng dụng có thể biên dịch được nhưng thất bại khi khởi động hoặc khi thực hiện một thao tác serialize/deserialize cụ thể.

Một số dấu hiệu thường gặp:

- `NoSuchMethodError`: code đã biên dịch gọi một method không tồn tại trong class được nạp lúc chạy.
- `NoClassDefFoundError`: class cần thiết không có trên runtime classpath hoặc không thể được khởi tạo.
- `NoSuchFieldError`: code mong đợi một field không tồn tại trong phiên bản class đang chạy.
- Lỗi tạo module hoặc lỗi cấu hình `ObjectMapper`: có thể liên quan đến API không tương thích, nhưng cũng có thể do cấu hình hoặc dữ liệu; cần đọc nguyên nhân gốc của stack trace.

Không nên kết luận mọi lỗi Jackson đều do lệch phiên bản. Hãy kiểm tra dependency graph và stack trace trước khi thay đổi dependency.

## 3. Dùng Jackson BOM để quản lý một bộ phiên bản

BOM (Bill of Materials) là một artifact công bố các dependency constraints cho một nhóm thư viện. Jackson cung cấp BOM tại tọa độ:

~~~text
com.fasterxml.jackson:jackson-bom
~~~

Khi import BOM, Gradle có thể áp dụng các phiên bản đã được định nghĩa cho các artifact Jackson. Những dependency thuộc bộ này không cần lặp lại phiên bản ở từng dòng khai báo.

Ví dụ với Gradle Groovy DSL:

~~~groovy
// Đặt jacksonBomVersion trong gradle.properties.
// Giá trị 2.x.y dưới đây là chỗ giữ chỗ; thay bằng bản phát hành
// được dự án lựa chọn và hỗ trợ.
def jacksonBomVersion = providers.gradleProperty("jacksonBomVersion").get()

dependencies {
    implementation platform(
        "com.fasterxml.jackson:jackson-bom:$jacksonBomVersion"
    )

    implementation "com.fasterxml.jackson.core:jackson-databind"
    implementation "com.fasterxml.jackson.datatype:jackson-datatype-jsr310"
    implementation "com.fasterxml.jackson.dataformat:jackson-dataformat-yaml"
}
~~~

Trong `gradle.properties`:

~~~properties
jacksonBomVersion=2.x.y
~~~

Thay `2.x.y` bằng một phiên bản BOM cụ thể đã được dự án lựa chọn. Không dùng chuỗi giữ chỗ này nguyên văn trong build thực tế.

Sau khi BOM được import:

- Các dependency Jackson được khai báo không cần chỉ định phiên bản riêng.
- Khi thêm một module Jackson mới, hãy kiểm tra module đó có thuộc BOM đang dùng hay không.
- Khi nâng cấp, thay phiên bản BOM tại một nơi rồi kiểm tra lại toàn bộ graph và các bài kiểm tra liên quan.
- Không đặt thêm phiên bản riêng cho `jackson-databind`, `jackson-core` hoặc module mở rộng nếu không có lý do tương thích đã được xác minh.

BOM không tự thêm tất cả artifact vào classpath. Nó chỉ quản lý phiên bản cho dependency mà ứng dụng thực sự khai báo hoặc nhận được từ dependency khác. Nếu ứng dụng không dùng YAML thì không cần thêm `jackson-dataformat-yaml` chỉ vì BOM có quản lý artifact đó.

Với Gradle, `platform(...)` đưa các constraints của BOM vào quá trình giải quyết dependency. Đây thường là cách phù hợp để giữ một bộ thư viện nhất quán trong khi vẫn cho phép Gradle xử lý các constraints khác của dự án. `enforcedPlatform(...)` có tính áp đặt mạnh hơn và có thể truyền ảnh hưởng đến consumer; chỉ dùng khi chính sách dependency của dự án thực sự yêu cầu hành vi đó.

## 4. Khi Spring Boot đã quản lý phiên bản Jackson

Trong ứng dụng Spring Boot, dependency management của Spring Boot thường đã cung cấp một bộ phiên bản Jackson phù hợp với phiên bản Boot đang sử dụng.

Nếu dự án dùng Spring Boot cùng plugin `io.spring.dependency-management`, Spring Boot có thể tự import BOM `spring-boot-dependencies`. Khi đó, dependency Jackson thường được khai báo mà không ghi phiên bản:

~~~groovy
dependencies {
    implementation "com.fasterxml.jackson.core:jackson-databind"
    implementation "com.fasterxml.jackson.datatype:jackson-datatype-jsr310"
}
~~~

Chỉ khai báo module mà ứng dụng thực sự cần. Một số starter của Spring Boot đã đưa sẵn Jackson hoặc module ngày giờ vào dependency graph, vì vậy hãy kiểm tra trước khi thêm dependency trực tiếp trùng lặp.

Nếu dự án dùng Gradle native BOM support thay cho plugin dependency management, có thể import BOM của Spring Boot dưới dạng platform:

~~~groovy
dependencies {
    implementation platform(
        "org.springframework.boot:spring-boot-dependencies:$springBootVersion"
    )

    implementation "com.fasterxml.jackson.core:jackson-databind"
}
~~~

Trong cấu hình này, `springBootVersion` phải là phiên bản Spring Boot mà dự án đang sử dụng.

**Chọn một nguồn quản lý phiên bản có chủ đích.** Nếu Spring Boot đã quản lý Jackson, đừng thêm một Jackson BOM độc lập chỉ vì muốn tất cả dependency có cùng một phiên bản nhìn thấy được. Hai BOM có thể đưa ra các constraints khác nhau. Khi cần nâng cấp Jackson vượt khỏi tập phiên bản do Spring Boot quản lý, hãy xác minh tổ hợp đó được Spring Boot và các integration đang dùng hỗ trợ, sau đó cấu hình override tập trung và kiểm tra toàn bộ runtime.

Spring Boot không chỉ quản lý Jackson. Nó còn phối hợp nhiều thư viện trong hệ sinh thái Spring. Tự nâng riêng Jackson có thể làm mất tổ hợp tương thích mà Boot đã kiểm thử. Nếu yêu cầu nâng cấp bắt nguồn từ một bản vá bảo mật, hãy kiểm tra hướng nâng cấp được hỗ trợ của phiên bản Spring Boot hiện tại trước khi override một artifact riêng lẻ.

## 5. Dependency bắc cầu có thể đưa phiên bản khác vào

Ứng dụng thường không khai báo trực tiếp mọi thư viện. Một starter, SDK hoặc thư viện tích hợp có thể phụ thuộc vào Jackson. Đây là dependency bắc cầu (transitive dependency).

Ví dụ:

~~~text
application
├── spring-boot-starter-web
│   └── jackson-databind
│       ├── jackson-core
│       └── jackson-annotations
├── third-party-sdk
│   └── jackson-databind
└── jackson-datatype-jsr310
~~~

Hai nhánh có thể yêu cầu các phiên bản khác nhau. Nếu không có BOM hoặc chính sách dependency management phù hợp, phiên bản được chọn cho từng artifact có thể không tạo thành một bộ Jackson tương thích.

Không nên xử lý tình huống này bằng cách thêm ngẫu nhiên một dependency mới với phiên bản cao hơn. Làm vậy có thể chỉ thay đổi một artifact và khiến độ lệch giữa các thành phần lớn hơn.

Hãy xác định dependency nào đang yêu cầu phiên bản không mong muốn, sau đó chọn một trong các hướng:

1. Dùng BOM chung để quản lý toàn bộ artifact Jackson thuộc phạm vi BOM.
2. Nâng hoặc hạ thư viện bên thứ ba lên phiên bản tương thích với bộ Jackson đã chọn.
3. Nếu thư viện bên thứ ba có yêu cầu đặc biệt, xác minh yêu cầu đó và kiểm thử tổ hợp cụ thể trước khi áp dụng.
4. Chỉ loại trừ dependency bắc cầu khi đã biết dependency thay thế nào sẽ cung cấp class cần thiết và không làm mất chức năng khác.

Exclusion không phải cách sửa mặc định. Nếu loại `jackson-core` khỏi một nhánh nhưng runtime không có dependency khác cung cấp nó, ứng dụng sẽ thiếu class. Nếu thay bằng phiên bản khác không tương thích, lỗi chỉ chuyển sang thời điểm chạy.

## 6. Không trộn các major version

Khi nâng cấp một thư viện lớn, cần phân biệt nâng cấp trong cùng major line với migration sang major line mới.

Ví dụ, các artifact thuộc Jackson 2.x và Jackson 3.x không thể được xem như những phiên bản thay thế trực tiếp cho nhau. Major release có thể thay đổi package, tọa độ artifact, API, yêu cầu Java và cách tích hợp với framework.

Không nên nâng riêng `jackson-databind` sang major mới trong khi `jackson-core`, annotations hoặc module mở rộng vẫn thuộc major cũ. Cũng không nên giả định module cũ có thể chạy nguyên trạng chỉ vì tên chức năng tương tự.

Một migration major cần được xem như một thay đổi có phạm vi:

- Kiểm tra hướng dẫn migration và yêu cầu nền tảng Java.
- Kiểm tra package import, tọa độ dependency và API được sử dụng.
- Kiểm tra các module mở rộng mà ứng dụng đang dùng có bản tương ứng hay không.
- Kiểm tra Spring Boot hoặc framework tích hợp có hỗ trợ major mới hay chưa.
- Cập nhật cấu hình, module đăng ký, custom serializer/deserializer và annotation nếu cần.
- Chạy kiểm tra serialize/deserialize, API contract và integration test trên runtime thực tế.

Nếu framework đang quản lý Jackson 2.x, không nên tự đưa một thành phần Jackson 3.x vào classpath với kỳ vọng nó sẽ hoạt động cùng cấu hình cũ. Hãy thực hiện migration theo một tổ hợp được hỗ trợ và có kiểm chứng.

## 7. Kiểm tra phiên bản Gradle thực sự đã chọn

Khai báo trong `build.gradle` cho biết dự án yêu cầu gì. Dependency report mới cho biết Gradle đã giải quyết thành gì.

Xem toàn bộ runtime dependency tree của module:

~~~powershell
.\gradlew.bat :<module-path>:dependencies --configuration runtimeClasspath
~~~

Thay `<module-path>` bằng Gradle project path thực tế, ví dụ `:my-module`.

Dùng `dependencyInsight` để tìm lý do một artifact được chọn:

~~~powershell
.\gradlew.bat :<module-path>:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
.\gradlew.bat :<module-path>:dependencyInsight --dependency jackson-core --configuration runtimeClasspath
.\gradlew.bat :<module-path>:dependencyInsight --dependency jackson-annotations --configuration runtimeClasspath
.\gradlew.bat :<module-path>:dependencyInsight --dependency jackson-datatype-jsr310 --configuration runtimeClasspath
~~~

Lệnh này giúp trả lời:

- Dependency nào yêu cầu artifact?
- Có nhiều phiên bản được yêu cầu hay không?
- Phiên bản nào được chọn?
- Phiên bản được chọn do constraint, platform hay quy tắc conflict resolution nào?

Hãy kiểm tra cả `compileClasspath` khi cần đối chiếu với `runtimeClasspath`:

~~~powershell
.\gradlew.bat :<module-path>:dependencies --configuration compileClasspath
~~~

Không phải module nào cũng có cả hai configuration với tên giống nhau. Dùng configuration tồn tại trong module đang kiểm tra.

Khi đọc report, hãy tập trung vào toàn bộ nhóm Jackson có mặt, đặc biệt là core, annotations, databind và các module mở rộng. Một report chỉ cho thấy `jackson-databind` có phiên bản mong muốn chưa đủ để kết luận cả bộ đã đồng bộ.

## 8. Quản lý phiên bản ổn định trong dự án nhiều module

Trong Gradle multi-project, nhiều module có thể cùng sử dụng Jackson. Nếu mỗi module tự khai báo phiên bản, việc nâng cấp sẽ dễ bị lệch và khó kiểm soát.

Có thể tập trung chính sách ở một trong các cơ chế sau, tùy kiến trúc build:

- Một BOM được import trong convention plugin hoặc dependency management chung.
- Version catalog dùng chung để tập trung khai báo alias và phiên bản BOM.
- Dependency constraints tại cấp build phù hợp với phạm vi áp dụng.
- BOM của Spring Boot nếu toàn bộ ứng dụng đang theo dependency management của Spring Boot.

Ví dụ version catalog:

~~~toml
[versions]
jackson-bom = "2.x.y"

[libraries]
jackson-bom = { module = "com.fasterxml.jackson:jackson-bom", version.ref = "jackson-bom" }
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind" }
jackson-jsr310 = { module = "com.fasterxml.jackson.datatype:jackson-datatype-jsr310" }
~~~

Sử dụng trong Gradle:

~~~groovy
dependencies {
    implementation platform(libs.jackson.bom)
    implementation libs.jackson.databind
    implementation libs.jackson.jsr310
}
~~~

Phiên bản `2.x.y` vẫn là chỗ giữ chỗ và phải được thay bằng phiên bản đã phê duyệt. Nếu Spring Boot BOM đã là nguồn quản lý chính, hãy dùng cơ chế đó thay vì tạo thêm một nguồn phiên bản song song.

Tập trung quản lý không có nghĩa là ép mọi module phải phụ thuộc Jackson. Module nào không cần Jackson thì không nên thêm dependency chỉ để đồng nhất file build. Chính sách chung chỉ có tác dụng với module thực sự sử dụng các artifact đó.

Khi một module là thư viện được công bố cho ứng dụng khác, cần kiểm tra thêm cách dependency constraints được truyền đến consumer. Không nên vô tình áp đặt một phiên bản quá rộng lên ứng dụng sử dụng thư viện nếu hợp đồng dependency của thư viện không yêu cầu điều đó.

## 9. Khóa dependency để tái lập kết quả build

BOM giúp chọn một bộ phiên bản tương thích, nhưng build vẫn có thể thay đổi nếu dùng phiên bản động, repository thay đổi artifact hoặc dependency graph không được khóa.

Gradle dependency locking có thể ghi lại phiên bản đã được giải quyết. Ví dụ cấu hình:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau đó chạy task có resolve configuration cần khóa cùng tùy chọn `--write-locks`:

~~~powershell
.\gradlew.bat :<module-path>:dependencies --configuration runtimeClasspath --write-locks
~~~

Kiểm tra và commit lock state theo quy trình của dự án. Khi nâng cấp BOM, cập nhật lock state có chủ đích rồi review các phiên bản thay đổi.

Dependency locking và BOM giải quyết hai vấn đề khác nhau:

- BOM mô tả tập phiên bản được phối hợp và các constraints.
- Locking ghi lại phiên bản đã được một lần resolve để những lần build sau có thể tái lập kết quả.

Nếu dự án dùng dependency verification, checksum verification bổ sung khả năng kiểm tra artifact tải về có khớp metadata đã phê duyệt hay không. Verification không thay thế BOM, dependency locking hoặc kiểm thử tương thích.

Không dùng dynamic version như `2.+` cho dependency Jackson trong build cần tái lập. Một lần resolve sau có thể chọn phiên bản khác mà file build không thay đổi, làm kết quả kiểm tra giữa các máy hoặc giữa CI và local khó so sánh.

## 10. Quy trình nâng cấp Jackson có kiểm soát

Khi cần nâng cấp, hãy thực hiện theo trình tự có thể review:

1. **Xác định nguồn quản lý hiện tại.** Kiểm tra Jackson BOM, Spring Boot BOM, version catalog, convention plugin và các constraint đang áp dụng.
2. **Thu thập dependency graph hiện tại.** Lưu report của runtimeClasspath và dùng dependencyInsight cho các artifact Jackson quan trọng.
3. **Xác định lý do nâng cấp.** Có thể là bản vá bảo mật, lỗi tương thích, yêu cầu module mới hoặc thay đổi major. Mục tiêu nâng cấp quyết định phạm vi kiểm tra.
4. **Chọn một bộ phiên bản được hỗ trợ.** Ưu tiên BOM và ma trận tương thích của framework. Với ứng dụng Spring Boot, kiểm tra phiên bản Jackson mà Boot đang quản lý và hướng override được hỗ trợ.
5. **Cập nhật tại nguồn quản lý tập trung.** Không sửa rải rác phiên bản của từng artifact nếu BOM đã có thể quản lý chúng.
6. **Resolve lại dependency graph.** Xác nhận core, annotations, databind và module mở rộng không bị lệch ngoài dự kiến.
7. **Chạy kiểm thử.** Bao gồm serialize, deserialize, thời gian, enum, custom serializer/deserializer, JSON mẫu từ producer/consumer và integration test.
8. **Đọc lại kết quả runtime.** Một build thành công chưa đủ nếu code path Jackson quan trọng chưa được thực thi.
9. **Cập nhật lock state và review thay đổi.** Xác định rõ artifact nào đổi phiên bản và vì sao.

Nếu nâng cấp để xử lý lỗ hổng, không chỉ kiểm tra riêng `jackson-databind` rồi dừng lại. Hãy xác minh toàn bộ artifact liên quan, phiên bản được framework hỗ trợ và các module ứng dụng thực sự dùng. Bản vá có thể yêu cầu nâng cả tập Jackson hoặc nâng Spring Boot lên một bản phù hợp.

## 11. Những cách làm dễ tạo ra lỗi phiên bản

| Cách làm | Hệ quả có thể gặp | Cách xử lý phù hợp |
|---|---|---|
| Ghi phiên bản riêng ở nhiều dependency Jackson | Các module có thể lệch nhau khi chỉ nâng một dòng. | Quản lý tập trung bằng BOM hoặc framework BOM. |
| Chỉ nâng `jackson-databind` | Core, annotations hoặc module mở rộng có thể không tương thích. | Nâng theo bộ phiên bản được BOM quản lý. |
| Thêm Jackson BOM bên cạnh Spring Boot BOM mà không kiểm tra | Hai nguồn constraint có thể đưa ra kết quả không mong muốn. | Chọn một nguồn quản lý chính và xác minh override nếu thật sự cần. |
| Dùng `resolutionStrategy.force` cho một artifact | Có thể ép một module riêng lẻ và che khuất nguyên nhân xung đột. | Dùng platform/constraints có phạm vi phù hợp; chỉ force khi đã có lý do cụ thể. |
| Exclude dependency bắc cầu theo cảm tính | Runtime có thể thiếu class hoặc dùng bộ thư viện không tương thích. | Xác định dependency thay thế và kiểm tra graph sau exclusion. |
| Dùng phiên bản động | Build có thể thay đổi giữa các lần resolve. | Dùng phiên bản cụ thể, BOM và dependency locking. |
| Nâng major version từng artifact | Trộn API và module của hai major line. | Lập migration đồng bộ cho toàn bộ hệ sinh thái Jackson và framework. |
| Chỉ chạy compile/test đơn giản | Lỗi chỉ xuất hiện khi một serializer hoặc module cụ thể được gọi. | Thêm kiểm tra runtime cho các đường serialize/deserialize thực tế. |

## 12. Ví dụ kiểm tra một bộ Jackson sau khi thay đổi

Giả sử ứng dụng sử dụng `ObjectMapper`, `JavaTimeModule` và YAML. Sau khi cập nhật BOM, cần kiểm tra:

~~~text
Runtime classpath
├── jackson-core
├── jackson-annotations
├── jackson-databind
├── jackson-datatype-jsr310
└── jackson-dataformat-yaml
~~~

Danh sách trên là các thành phần ứng dụng mong đợi, không phải cam kết rằng mọi phiên bản của chúng phải có cùng số phiên bản. Hãy đối chiếu từng artifact với kết quả BOM và dependencyInsight.

Một bài kiểm tra chức năng tối thiểu nên xác nhận:

- ObjectMapper được tạo thành công với các module cần thiết.
- Một DTO có enum được serialize thành wire value đã thống nhất.
- DTO có `Instant` hoặc `LocalDate` được serialize và deserialize theo định dạng hợp đồng.
- BigDecimal giữ được giá trị thập phân mong muốn.
- JSON mẫu từ hệ thống bên ngoài có thể deserialize.
- YAML hoặc định dạng bổ sung hoạt động nếu ứng dụng thực sự sử dụng module tương ứng.

Ví dụ kiểm tra module ngày giờ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();

String json = mapper.writeValueAsString(
    new EventResponse("EV-01", Instant.parse("2026-11-12T08:15:30Z"))
);

EventResponse restored =
    mapper.readValue(json, EventResponse.class);
~~~

Đoạn code chỉ minh họa đường sử dụng cần kiểm tra; lớp `EventResponse` cần được định nghĩa trong test hoặc source của ứng dụng. Bài kiểm tra cần xác nhận cả JSON đầu ra và object nhận lại, không chỉ xác nhận rằng lời gọi không ném exception.

## Kết luận

Các thành phần Jackson phối hợp qua API và dependency bắc cầu. Gradle giải quyết phiên bản theo từng artifact, nên một runtime classpath có thể chứa các phiên bản Jackson không đồng bộ dù build vẫn biên dịch thành công.

Hãy dùng một nguồn quản lý phiên bản rõ ràng: Jackson BOM cho ứng dụng tự quản lý Jackson, hoặc Spring Boot BOM khi framework đã quản lý tập dependency. Kiểm tra dependencyInsight trên runtime classpath, kiểm thử các đường serialize/deserialize thực tế và khóa dependency khi cần tái lập build. Khi nâng major version, hãy migration toàn bộ tổ hợp Jackson cùng framework tích hợp thay vì nâng từng artifact riêng lẻ.

