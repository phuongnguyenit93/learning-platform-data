# Phiên bản cố định, khoảng phiên bản và bộ chọn phiên bản động

Khi khai báo dependency trong Gradle, phần phiên bản quyết định những phiên bản thư viện nào được phép tham gia quá trình phân giải. Có thể yêu cầu một phiên bản cụ thể, giới hạn trong một khoảng, hoặc dùng bộ chọn động để Gradle tìm phiên bản phù hợp tại thời điểm phân giải.

Ba cách này có mức độ kiểm soát và tính ổn định khác nhau. Phiên bản cố định giúp build dễ dự đoán hơn; khoảng phiên bản cho phép cập nhật trong một phạm vi; bộ chọn động giúp tự nhận phiên bản mới nhưng khiến kết quả có thể thay đổi theo thời gian. Muốn chọn đúng cách, cần hiểu cả cú pháp khai báo lẫn quy tắc Gradle giải quyết xung đột phiên bản giữa dependency trực tiếp, dependency bắc cầu và constraint.

## 1. Phiên bản dependency nằm ở đâu?

Một dependency bên ngoài thường được xác định bằng tọa độ gồm group, module và version:

~~~text
group:module:version
~~~

Ví dụ:

~~~text
org.apache.commons:commons-lang3:3.14.0
~~~

Trong đó:

- **group** xác định nhóm hoặc tổ chức phát hành thư viện.
- **module** là tên module hoặc artifact.
- **version** là phiên bản được yêu cầu.

Trong Gradle Groovy DSL, dependency có thể được khai báo như sau:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Trong Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

Gradle dùng thông tin này để tìm module trong repository đã cấu hình, đọc metadata và xác định các dependency mà module đó cần. Phiên bản ghi trong build script là một phần của yêu cầu phân giải; kết quả cuối cùng còn chịu ảnh hưởng của các dependency khác, constraint, platform và quy tắc resolution strategy.

Một điểm cần phân biệt: khai báo dependency cho biết ứng dụng cần module đó; khai báo dependency constraint chỉ đặt quy tắc về phiên bản nếu module xuất hiện trong graph. Constraint không tự thêm module mới vào graph.

## 2. Phiên bản cố định (fixed version)

Phiên bản cố định là cách khai báo một số phiên bản cụ thể, ví dụ **3.14.0**:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
~~~

Khi đọc build script, người phát triển có thể biết phiên bản được yêu cầu mà không cần suy luận từ một khoảng hay một bộ chọn động.

### Ưu điểm

- Kết quả dễ dự đoán hơn khi build lại trong cùng một cấu hình dependency.
- Dễ điều tra lỗi phát sinh sau khi nâng cấp thư viện.
- Code review có thể nhận biết rõ thay đổi phiên bản.
- Giảm nguy cơ một build hôm nay và một build ngày mai tự chọn các bản phát hành khác nhau chỉ vì repository có thêm phiên bản mới.

### Giới hạn cần hiểu

Một phiên bản được viết cụ thể vẫn là một **version request**. Trong quá trình giải quyết xung đột, Gradle thường chọn phiên bản cao nhất trong các yêu cầu tương thích của cùng module. Vì vậy, nếu một dependency trực tiếp yêu cầu **1.4.0** nhưng dependency bắc cầu yêu cầu **1.6.0**, kết quả có thể là **1.6.0**.

Ví dụ:

~~~kotlin
dependencies {
    implementation("com.example:client:1.0.0")
    implementation("com.example:shared-library:1.4.0")
}
~~~

Giả sử **client:1.0.0** phụ thuộc vào **shared-library:1.6.0**. Cả yêu cầu trực tiếp **1.4.0** và yêu cầu bắc cầu **1.6.0** cùng tham gia phân giải. Với quy tắc mặc định, Gradle thường chọn **1.6.0** để giải quyết xung đột.

Do đó, không nên đồng nhất hai ý sau:

- **Khai báo version cố định:** build script yêu cầu một phiên bản cụ thể.
- **Khóa chặt phiên bản:** cấu hình buộc kết quả phải tuân theo đúng phiên bản hoặc giới hạn nghiêm ngặt đã đặt.

Nếu cần giới hạn nghiêm ngặt, có thể dùng rich version constraint với **strictly**, hoặc dùng dependency locking để ghi lại phiên bản đã phân giải.

## 3. Khoảng phiên bản (version range)

Khoảng phiên bản cho phép Gradle chọn một phiên bản nằm trong một phạm vi. Cách viết thường dùng dấu ngoặc vuông và ngoặc tròn để biểu thị giới hạn bao gồm hay loại trừ.

| Cú pháp | Ý nghĩa |
|---|---|
| **[1.2,2.0)** | Từ 1.2 trở lên, nhỏ hơn 2.0 |
| **[1.2,2.0]** | Từ 1.2 đến 2.0, bao gồm cả hai đầu |
| **(1.2,2.0]** | Lớn hơn 1.2 và nhỏ hơn hoặc bằng 2.0 |
| **[1.2,)** | Từ 1.2 trở lên, không đặt giới hạn trên |
| **(,2.0)** | Nhỏ hơn 2.0, không đặt giới hạn dưới |

Ví dụ khai báo trong Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.example:library:[1.2,2.0)")
}
~~~

Với khoảng **[1.2,2.0)**, các phiên bản như **1.2**, **1.5.3** hoặc **1.9.9** nằm trong phạm vi; phiên bản **2.0** không nằm trong phạm vi vì giới hạn trên là loại trừ.

Một khoảng phiên bản không bảo đảm rằng mọi phiên bản bên trong đều tương thích với ứng dụng. Gradle chỉ có thể phân giải dựa trên metadata và quy tắc phiên bản; nó không thể tự chứng minh API, hành vi hoặc dữ liệu của các bản phát hành đều tương thích với mã nguồn của bạn.

### Khi nào nên dùng version range?

Khoảng phiên bản có thể hữu ích khi:

- Một thư viện công bố cam kết tương thích trong một dải phiên bản.
- Một module nội bộ cho phép các phiên bản trong một giới hạn đã được kiểm soát.
- Người phát triển muốn chấp nhận bản vá hoặc bản cập nhật nhỏ nhưng tránh một thế hệ API mới.

Ví dụ, nhóm có thể đặt khoảng **[2.4,3.0)** nếu chính sách tương thích của thư viện cho phép các phiên bản 2.x. Tuy nhiên, cần có kiểm thử để xác nhận từng bản phát hành mới không làm hỏng ứng dụng.

### Rủi ro của khoảng phiên bản

Kết quả có thể thay đổi khi repository có thêm phiên bản phù hợp. Ví dụ, lần đầu Gradle phân giải khoảng **[1.2,2.0)** có thể chọn **1.5.0**; sau đó repository phát hành **1.8.0**, lần phân giải tiếp theo có thể chọn bản mới hơn.

Điều này khiến cùng một build script có thể nhận dependency khác nhau ở những thời điểm khác nhau. Nếu muốn build có thể tái lập, cần kết hợp chính sách version range với dependency locking hoặc cơ chế kiểm soát phiên bản phù hợp.

## 4. Bộ chọn phiên bản động (dynamic version selector)

Bộ chọn phiên bản động cho phép Gradle tìm phiên bản phù hợp theo một mẫu hoặc trạng thái phát hành thay vì chỉ định một bản cụ thể.

Một số dạng phổ biến:

| Bộ chọn | Ý nghĩa khái quát |
|---|---|
| **1.+** | Chọn phiên bản mới nhất phù hợp với tiền tố 1 |
| **latest.release** | Chọn bản phát hành mới nhất được xem là release |
| **latest.integration** | Chọn bản mới nhất thuộc dòng integration, có thể bao gồm bản chưa phải release |
| **[1.0,2.0)** | Chọn phiên bản mới nhất nằm trong khoảng đã chỉ định |

Ví dụ:

~~~kotlin
dependencies {
    implementation("com.example:library:1.+")
}
~~~

Với selector **1.+**, Gradle tìm các phiên bản có tiền tố tương ứng và chọn bản phù hợp mới nhất theo quy tắc so sánh phiên bản. Nếu repository hiện có **1.4.0**, sau đó xuất hiện **1.5.0**, kết quả có thể chuyển từ **1.4.0** sang **1.5.0** sau khi thông tin động được làm mới.

Một ví dụ khác:

~~~kotlin
dependencies {
    implementation("com.example:library:latest.release")
}
~~~

Bộ chọn **latest.release** phù hợp khi muốn nhận bản release mới nhất mà metadata của repository công bố. **latest.integration** rộng hơn và có thể chọn bản đang phát triển hoặc bản tích hợp mới hơn, tùy metadata và trạng thái phát hành.

Không nên dùng **latest.integration** cho một ứng dụng cần build ổn định nếu nhóm không có quy trình kiểm thử và kiểm soát cập nhật chặt chẽ.

### Dynamic selector không có nghĩa là luôn tải bản mới nhất ở mọi lần chạy

Gradle lưu cache thông tin phiên bản động để tránh truy vấn repository liên tục. Theo cấu hình mặc định, kết quả của dynamic version selector được cache trong một khoảng thời gian (thông thường là 24 giờ). Vì vậy, repository vừa có phiên bản mới không có nghĩa lần chạy kế tiếp lập tức chọn phiên bản đó.

Có thể điều chỉnh thời gian cache động:

~~~kotlin
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor(10, "minutes")
    }
}
~~~

Trong Groovy DSL:

~~~groovy
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor 10, 'minutes'
    }
}
~~~

Giảm thời gian cache làm Gradle kiểm tra thông tin phiên bản thường xuyên hơn, nhưng có thể tăng số lần truy vấn repository và khiến kết quả build thay đổi nhanh hơn.

## 5. So sánh ba cách khai báo

| Tiêu chí | Phiên bản cố định | Khoảng phiên bản | Bộ chọn động |
|---|---|---|---|
| Ví dụ | **1.4.0** | **[1.2,2.0)** | **1.+**, **latest.release** |
| Phạm vi được chấp nhận | Một phiên bản được yêu cầu | Các phiên bản trong phạm vi | Phụ thuộc mẫu hoặc trạng thái phát hành |
| Khả năng tự nhận bản mới | Thấp hơn | Có, khi có bản mới trong phạm vi | Có, khi selector được phân giải lại |
| Tính dễ dự đoán | Cao hơn, nhưng vẫn chịu conflict resolution | Thấp hơn | Thấp hơn |
| Phù hợp với | Ứng dụng cần kiểm soát phiên bản | Thư viện có chính sách tương thích rõ ràng | Thử nghiệm hoặc quy trình cập nhật tự động có kiểm soát |

Không có một cách khai báo phù hợp cho mọi dự án. Lựa chọn phụ thuộc vào mục tiêu: ưu tiên build ổn định, chấp nhận cập nhật trong giới hạn, hay chủ động nhận bản phát hành mới.

## 6. Gradle giải quyết xung đột phiên bản như thế nào?

Một dependency có thể được yêu cầu bởi nhiều nhánh khác nhau trong graph. Ví dụ:

~~~text
Ứng dụng
├── library-a:1.0
│   └── shared:1.4
└── library-b:2.0
    └── shared:1.6
~~~

Hai thư viện cùng yêu cầu module **shared**, nhưng một bên yêu cầu **1.4** và bên còn lại yêu cầu **1.6**.

Với quy tắc conflict resolution mặc định, Gradle thường chọn phiên bản cao hơn, trong ví dụ là **shared:1.6**. Kết quả có thể hiển thị trong báo cáo dependency như sau:

~~~text
com.example:shared:1.4 -> 1.6
~~~

Dấu **->** cho biết phiên bản được yêu cầu hoặc xuất hiện trong graph đã được thay bằng phiên bản được chọn sau phân giải.

### Dependency trực tiếp không luôn thắng dependency bắc cầu

Một hiểu lầm thường gặp là dependency khai báo trực tiếp trong build script luôn được ưu tiên hơn dependency do thư viện khác kéo vào. Với cơ chế conflict resolution thông thường, Gradle không mặc định ưu tiên dependency trực tiếp chỉ vì nó được khai báo ở project hiện tại.

Nếu cần hiểu phiên bản nào đang được dùng và tại sao, hãy xem báo cáo dependency thay vì chỉ đọc một dòng trong build script.

### Dùng dependencyInsight để tìm nguyên nhân

Lệnh **dependencyInsight** cho biết một module được đưa vào configuration nào, phiên bản nào được chọn và những yêu cầu nào tham gia phân giải.

Ví dụ:

~~~bash
./gradlew dependencyInsight --dependency shared --configuration runtimeClasspath
~~~

Trong dự án nhiều module:

~~~bash
./gradlew :app:dependencyInsight --dependency shared --configuration runtimeClasspath
~~~

Có thể xem toàn bộ cây dependency của configuration:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Khi đọc kết quả, chú ý:

- Phiên bản được chọn cuối cùng.
- Phiên bản mà từng dependency yêu cầu.
- Đường đi từ dependency gốc đến module đang kiểm tra.
- Các lý do lựa chọn hoặc quy tắc ảnh hưởng đến kết quả.

Đây là cách thực tế để giải thích vì sao một phiên bản cụ thể xuất hiện trong runtime classpath dù build script của module ứng dụng khai báo phiên bản khác.

## 7. Dùng rich version constraints để kiểm soát lựa chọn

Gradle hỗ trợ rich version declaration để mô tả yêu cầu chi tiết hơn một chuỗi phiên bản đơn lẻ.

Các thuộc tính thường gặp:

- **require:** phiên bản hoặc giới hạn được yêu cầu; vẫn tham gia cơ chế conflict resolution thông thường.
- **strictly:** giới hạn nghiêm ngặt; phiên bản được chọn phải thỏa mãn giới hạn này. Nếu không có phiên bản phù hợp, quá trình phân giải có thể thất bại.
- **prefer:** phiên bản được ưu tiên khi không có yêu cầu mạnh hơn buộc chọn phiên bản khác.
- **reject:** liệt kê phiên bản không được chấp nhận.
- **rejectAll:** từ chối mọi phiên bản trong một khai báo rich version.

### Khóa nghiêm ngặt một phiên bản

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.example:shared") {
        version {
            strictly("1.4.0")
        }
    }
}
~~~

Cách khai báo này yêu cầu đúng phiên bản **1.4.0**. Nếu một dependency khác yêu cầu phiên bản không tương thích với giới hạn nghiêm ngặt, Gradle có thể báo lỗi phân giải thay vì âm thầm chọn một bản khác.

### Giới hạn trong một khoảng và ưu tiên một bản

~~~kotlin
dependencies {
    implementation("com.example:shared") {
        version {
            strictly("[1.4,2.0)")
            prefer("1.6.2")
            reject("1.5.0")
        }
    }
}
~~~

Ý nghĩa:

- Chỉ chấp nhận phiên bản từ **1.4** trở lên và nhỏ hơn **2.0**.
- Ưu tiên **1.6.2** nếu không có lý do mạnh hơn để chọn phiên bản khác.
- Không chấp nhận **1.5.0**.

Nếu không có phiên bản nào thỏa mãn các quy tắc, Gradle sẽ không thể phân giải dependency thành công. Đây là điều hữu ích khi nhóm muốn phát hiện xung đột sớm thay vì tự động chấp nhận một phiên bản không tương thích.

### Đặt constraint riêng

Có thể khai báo constraint trong khối **constraints**:

~~~kotlin
dependencies {
    implementation("com.example:client:2.0.0")

    constraints {
        implementation("com.example:shared") {
            version {
                strictly("1.6.2")
            }
            because("Các module của ứng dụng cần cùng một phiên bản shared")
        }
    }
}
~~~

Constraint này ảnh hưởng đến cách Gradle phân giải **shared** nếu module đó được đưa vào graph. Nó không tự thêm **shared** vào dependency graph nếu không có dependency nào yêu cầu module đó.

Dùng **because** để ghi lại lý do của constraint giúp người bảo trì hiểu vì sao giới hạn phiên bản được đặt ra.

## 8. Dùng version catalog để quản lý phiên bản tập trung

Với dự án có nhiều module, việc lặp lại cùng một version string trong nhiều build script dễ gây sai lệch. Gradle version catalog cho phép khai báo phiên bản và alias dependency trong một tệp tập trung, thường là **gradle/libs.versions.toml**.

Ví dụ:

~~~toml
[versions]
commonsLang = "3.14.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commonsLang" }
~~~

Sau đó dùng alias trong Kotlin DSL:

~~~kotlin
dependencies {
    implementation(libs.commons.lang3)
}
~~~

Version catalog giúp:

- Tập trung tên và phiên bản dependency.
- Tái sử dụng cùng alias giữa các module.
- Giảm lỗi gõ sai group, module hoặc version.
- Làm cho thay đổi phiên bản dễ tìm trong code review.

Tuy nhiên, version catalog chỉ là nơi khai báo dependency và version request. Nó không tự khóa toàn bộ phiên bản bắc cầu và không thay thế dependency locking. Nếu một dependency khác yêu cầu phiên bản cao hơn, kết quả phân giải vẫn có thể khác với version string trong catalog.

## 9. Dependency locking để giữ kết quả phân giải ổn định

Ngay cả khi build script dùng version range hoặc dynamic selector, nhóm vẫn có thể muốn các lần build thông thường sử dụng cùng một tập phiên bản đã được phân giải. **Dependency locking** ghi lại phiên bản đã chọn cho các configuration được bật khóa.

Trong Kotlin DSL:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Trong Groovy DSL:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi bật locking, chạy một task có phân giải dependency và yêu cầu ghi lock state:

~~~bash
./gradlew build --write-locks
~~~

Gradle tạo hoặc cập nhật tệp lock, thường có tên **gradle.lockfile** trong project. Tệp này ghi lại phiên bản đã phân giải để những lần build sau có thể dùng lại cùng kết quả, miễn là lock state còn hiệu lực và không có thay đổi cấu hình yêu cầu cập nhật.

Khi muốn cập nhật có chủ đích một số module, có thể dùng tùy chọn **--update-locks**:

~~~bash
./gradlew build --update-locks com.example:shared
~~~

Sau khi nâng cấp, hãy xem thay đổi trong lockfile cùng với thay đổi build script và kết quả kiểm thử. Không nên cập nhật lockfile một cách vô thức vì nó là một phần của thông tin xác định dependency thực tế mà ứng dụng sử dụng.

### Locking khác gì với version catalog?

| Cơ chế | Vai trò |
|---|---|
| Version catalog | Tập trung và tái sử dụng version request, alias dependency |
| Rich version constraint | Quy định phiên bản được phép, bị từ chối hoặc được ưu tiên |
| Dependency locking | Ghi lại phiên bản đã được phân giải cho configuration |
| Dependency verification | Kiểm tra tính toàn vẹn hoặc chữ ký của artifact được tải |

Các cơ chế này giải quyết những vấn đề khác nhau và có thể dùng kết hợp. Locking kiểm soát phiên bản đã chọn; verification giúp xác minh artifact tương ứng không bị thay đổi ngoài dự kiến.

## 10. Dynamic version cache và changing modules

Gradle cache metadata và artifact để tăng tốc quá trình phân giải. Hai khái niệm cần phân biệt:

- **Dynamic version:** selector có thể phân giải ra nhiều phiên bản khác nhau theo thời gian, ví dụ **1.+** hoặc **latest.release**.
- **Changing module:** tọa độ module giữ nguyên nhưng nội dung có thể thay đổi, ví dụ một module snapshot hoặc module được đánh dấu changing.

Theo mặc định, Gradle cache kết quả dynamic version và metadata của changing module trong một khoảng thời gian (thông thường 24 giờ). Có thể cấu hình riêng thời gian cache:

~~~kotlin
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor(10, "minutes")
        cacheChangingModulesFor(4, "hours")
    }
}
~~~

Trong Groovy DSL:

~~~groovy
configurations.configureEach {
    resolutionStrategy {
        cacheDynamicVersionsFor 10, 'minutes'
        cacheChangingModulesFor 4, 'hours'
    }
}
~~~

Với một dependency cụ thể, có thể đánh dấu module là changing:

~~~kotlin
dependencies {
    implementation("com.example:library:1.0-SNAPSHOT") {
        isChanging = true
    }
}
~~~

Các module có hậu tố **SNAPSHOT** từ Maven thường được Gradle xem là changing. Điều này phản ánh thực tế rằng cùng tọa độ snapshot có thể trỏ đến nội dung artifact mới theo thời gian.

Giảm thời gian cache có thể giúp nhận thay đổi sớm hơn, nhưng làm tăng truy vấn repository. Với build production, nên ưu tiên phiên bản phát hành bất biến và lock state thay vì dựa vào snapshot có nội dung thay đổi.

### Làm mới cache khi cần

Có thể yêu cầu Gradle làm mới thông tin dependency bằng:

~~~bash
./gradlew build --refresh-dependencies
~~~

Tùy chọn này buộc Gradle kiểm tra lại trạng thái dependency từ repository. Nó không có nghĩa là mọi artifact chắc chắn sẽ được tải lại toàn bộ; Gradle có thể dùng metadata hoặc checksum để xác định nội dung hiện tại vẫn hợp lệ.

Dùng **--refresh-dependencies** khi cần kiểm tra lại metadata hoặc khi nghi ngờ cache không phản ánh repository. Không nên thêm tùy chọn này vào mọi build thông thường vì có thể làm tăng thời gian và lưu lượng truy cập.

## 11. Quy trình chọn cách quản lý phiên bản

Có thể quyết định theo mục tiêu của dự án:

| Nhu cầu | Cách phù hợp |
|---|---|
| Build ứng dụng cần kết quả dễ dự đoán | Khai báo phiên bản cố định và bật dependency locking |
| Buộc một module dùng đúng phiên bản đã được phê duyệt | Dùng **strictly** hoặc constraint nghiêm ngặt |
| Cho phép cập nhật trong giới hạn tương thích đã kiểm chứng | Dùng version range có giới hạn và kiểm thử |
| Thử nghiệm bản phát hành mới nhất | Dùng dynamic selector trong môi trường thử nghiệm |
| Dùng cùng phiên bản ở nhiều module | Dùng version catalog hoặc platform |
| Giữ nguyên phiên bản đã phân giải giữa các máy và CI | Dùng dependency locking |
| Xác minh artifact không bị thay đổi | Bật dependency verification |

Với ứng dụng cần độ ổn định cao, một quy trình thường dùng là:

1. Khai báo phiên bản rõ ràng trong version catalog hoặc build script.
2. Dùng constraint hoặc platform để thống nhất các module có liên quan.
3. Bật dependency locking để lưu kết quả phân giải.
4. Chạy kiểm thử khi chủ động cập nhật dependency.
5. Review thay đổi version catalog và lockfile cùng nhau.
6. Dùng dependency verification nếu dự án cần kiểm tra checksum hoặc chữ ký artifact.

Với thư viện dùng lại trong nhiều ứng dụng, có thể cần chính sách version range rộng hơn, nhưng phải xác định rõ phạm vi tương thích và kiểm thử với các phiên bản được hỗ trợ.

## 12. Ví dụ thực hành: quan sát dynamic selector và kết quả phân giải

Giả sử dự án khai báo:

~~~kotlin
dependencies {
    implementation("com.example:shared:1.+")
}
~~~

Repository có các phiên bản **1.2.0**, **1.3.0** và **1.4.0**. Khi Gradle làm mới thông tin selector, nó có thể chọn **1.4.0**.

Để xem kết quả dependency của runtime classpath:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
~~~

Nếu cần biết vì sao **1.4.0** được chọn:

~~~bash
./gradlew :app:dependencyInsight --dependency shared --configuration runtimeClasspath
~~~

Giả sử nhóm quyết định chuyển sang phiên bản cố định:

~~~kotlin
dependencies {
    implementation("com.example:shared:1.4.0")
}
~~~

Sau đó bật dependency locking và ghi lock state:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

~~~bash
./gradlew :app:build --write-locks
~~~

Trong lần cập nhật tiếp theo, nhóm có thể đổi version request, chạy kiểm thử và cập nhật lockfile trong cùng một thay đổi được review. Nhờ vậy, người đọc biết rõ lý do nâng cấp và tập phiên bản thực tế mà build sử dụng.

Nếu kết quả vẫn khác kỳ vọng, hãy kiểm tra thêm dependency bắc cầu, platform, constraint, resolution strategy và lock state. Chỉ nhìn vào một khai báo dependency trực tiếp là chưa đủ để kết luận phiên bản cuối cùng.

## 13. Những lỗi và hiểu lầm thường gặp

| Hiểu lầm hoặc biểu hiện | Giải thích | Cách xử lý |
|---|---|---|
| Ghi **1.4.0** nghĩa là Gradle luôn dùng đúng **1.4.0** | Đây là version request; conflict resolution có thể chọn phiên bản cao hơn | Dùng **strictly** nếu cần giới hạn nghiêm ngặt; kiểm tra dependencyInsight |
| **1.+** luôn nhận bản mới nhất ngay lập tức | Dynamic selector có cache metadata | Kiểm tra cache policy; dùng refresh khi cần làm mới |
| Version range đảm bảo tương thích API | Range chỉ giới hạn tập phiên bản, không chứng minh tương thích | Xác định chính sách tương thích và chạy kiểm thử |
| Version catalog khóa toàn bộ dependency | Catalog tập trung version request, không khóa dependency bắc cầu | Dùng dependency locking nếu cần ghi kết quả phân giải |
| Dependency constraint tự thêm module vào graph | Constraint chỉ ảnh hưởng khi module được yêu cầu từ nơi khác | Khai báo dependency riêng nếu ứng dụng thực sự cần module |
| **--refresh-dependencies** luôn tải lại tất cả JAR | Gradle có thể xác minh cache bằng metadata hoặc checksum | Dùng lệnh này để làm mới thông tin khi cần, không coi nó là lệnh xóa toàn bộ cache |
| Phiên bản snapshot luôn bất biến | Snapshot có thể thay đổi nội dung dù tọa độ không đổi | Quản lý changing module cache và tránh dùng snapshot cho build cần tái lập |

## 14. Những nguyên tắc cần nhớ

- Phiên bản cố định giúp thể hiện rõ version request, nhưng không tự bảo đảm kết quả cuối cùng luôn đúng phiên bản đó khi có xung đột.
- Version range cho phép Gradle chọn trong một phạm vi; phạm vi càng rộng thì kết quả càng có thể thay đổi khi repository phát hành phiên bản mới.
- Dynamic selector như **1.+**, **latest.release** và **latest.integration** có thể chọn phiên bản khác nhau theo thời điểm phân giải và cache.
- Gradle thường giải quyết xung đột bằng cách chọn phiên bản cao hơn trong các yêu cầu tương thích; dùng **strictly** khi cần giới hạn nghiêm ngặt.
- Dùng **dependencyInsight** để tìm nguồn yêu cầu và lý do phiên bản được chọn.
- Version catalog giúp tập trung khai báo; rich version constraints đặt quy tắc; dependency locking ghi kết quả; dependency verification kiểm tra artifact.
- Dynamic version cache và changing module cache là hai chính sách riêng, có thể cấu hình thời gian khác nhau.
- Chỉ cập nhật dependency khi có lý do, kiểm thử và review thay đổi version request cùng lockfile.

Hiểu cách Gradle phân giải phiên bản giúp nhóm kiểm soát được thư viện nào thực sự đi vào classpath, giải thích vì sao phiên bản được chọn khác với khai báo ban đầu, và cân bằng giữa khả năng cập nhật với tính ổn định của build.
