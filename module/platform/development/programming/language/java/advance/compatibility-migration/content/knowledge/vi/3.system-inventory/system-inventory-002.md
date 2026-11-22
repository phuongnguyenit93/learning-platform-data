# Xác định phiên bản Java tối thiểu mà ứng dụng và thư viện cam kết hỗ trợ

Trong quá trình khảo sát hệ thống trước khi migration, một quyết định quan trọng là xác định phiên bản Java thấp nhất mà ứng dụng có thể và sẽ hỗ trợ. Kết quả này ảnh hưởng trực tiếp đến phiên bản JDK đích, lựa chọn framework và thư viện, cấu hình build, môi trường triển khai, ma trận kiểm thử và phạm vi người dùng có thể nâng cấp.

Không thể xác định phiên bản tối thiểu chỉ bằng cách nhìn vào JDK đang cài trên máy lập trình viên hoặc phiên bản được khai báo trong một file build. Cần xem xét đồng thời mã nguồn ứng dụng, bytecode, API Java được sử dụng, toàn bộ dependency cần thiết ở runtime, framework, application server, agent và cam kết hỗ trợ của nhà cung cấp.

## 1. Hiểu đúng về phiên bản Java tối thiểu

Phiên bản Java tối thiểu (minimum Java version hoặc minimum supported Java version) là phiên bản thấp nhất mà một thành phần được thiết kế, kiểm thử và tuyên bố hỗ trợ. Trong một hệ thống thực tế, có nhiều mức tối thiểu khác nhau; cần ghi rõ đang nói đến mức nào.

### 1.1. Phiên bản tối thiểu để chạy ứng dụng

Đây là phiên bản JRE/JDK thấp nhất mà ứng dụng có thể chạy trong môi trường được hỗ trợ. Mức này chịu ảnh hưởng bởi:

- Phiên bản bytecode của class trong ứng dụng và dependency.
- API nền tảng Java mà mã nguồn hoặc thư viện sử dụng.
- Yêu cầu Java của framework, application server, driver, agent và thư viện runtime.
- Các tính năng JVM hoặc cấu hình runtime mà ứng dụng phụ thuộc.
- Hệ điều hành, kiến trúc CPU và thư viện native được hỗ trợ.

Một ứng dụng có thể biên dịch thành công nhưng vẫn không chạy trên runtime thấp hơn nếu dependency yêu cầu bytecode hoặc API mới hơn.

### 1.2. Phiên bản tối thiểu để biên dịch

Đây là JDK thấp nhất có thể dùng để biên dịch mã nguồn theo cấu hình của dự án. Mức này có thể khác với phiên bản runtime.

Ví dụ, một dự án có thể dùng JDK 21 làm compiler nhưng đặt `--release 17` để tạo bytecode và giới hạn API nền tảng ở Java 17. Khi đó, build cần một JDK đủ mới theo yêu cầu của công cụ build, còn artifact được hướng đến runtime Java 17. Việc dùng compiler mới không tự động có nghĩa ứng dụng yêu cầu runtime cùng phiên bản.

### 1.3. Phiên bản tối thiểu để chạy quy trình build

Maven, Gradle, plugin, annotation processor, công cụ đóng gói và CI runner cũng có yêu cầu JDK riêng. Một phiên bản Gradle hoặc plugin có thể cần JDK mới để chạy, dù ứng dụng được biên dịch cho một runtime thấp hơn.

Vì vậy, cần ghi riêng:

| Phạm vi | Câu hỏi cần trả lời |
| --- | --- |
| Build JDK | JDK nào có thể chạy Maven/Gradle và các plugin của dự án? |
| Compile release | Mã nguồn được biên dịch theo API và bytecode của Java phiên bản nào? |
| Test JDK | Ứng dụng và bộ kiểm thử được chạy trên những phiên bản Java nào? |
| Runtime JDK | Phiên bản Java thấp nhất được hỗ trợ khi triển khai ứng dụng là gì? |
| Production support | Nhà cung cấp và tổ chức cam kết hỗ trợ vận hành trên những phiên bản nào? |

Không gộp các mức này thành một con số duy nhất nếu chúng có ý nghĩa khác nhau. Khi nói ứng dụng “hỗ trợ Java 17”, cần làm rõ đó là hỗ trợ chạy ứng dụng, build ứng dụng hay cả hai.

### 1.4. Phiên bản có thể chạy và phiên bản cam kết hỗ trợ

Một ứng dụng có thể tình cờ chạy trên Java 11 nhưng nhóm phát triển chỉ kiểm thử, vá lỗi và hỗ trợ production từ Java 17 trở lên. Trong trường hợp đó:

- Java 11 có thể là mức tương thích kỹ thuật đã quan sát được.
- Java 17 là mức hỗ trợ chính thức của sản phẩm.

Khi khảo sát để migration, cần xác định cả hai nếu có thể. Phiên bản tối thiểu được công bố cho khách hàng hoặc hệ thống phụ thuộc nên dựa trên cam kết có bằng chứng và có thể kiểm thử, không dựa vào phỏng đoán rằng “có lẽ vẫn chạy”.

## 2. Phạm vi cần khảo sát

Trước khi thu thập phiên bản, hãy xác định chính xác đơn vị triển khai và đường chạy cần hỗ trợ.

### 2.1. Xác định đơn vị ứng dụng

Với hệ thống một ứng dụng, có thể khảo sát artifact triển khai chính như JAR, WAR hoặc EAR. Với hệ thống nhiều service, hãy lập kết quả riêng cho từng service vì chúng có thể có dependency và vòng đời nâng cấp khác nhau.

Với ứng dụng nhiều module, cần phân biệt:

- Module được đóng gói và triển khai cùng nhau.
- Module được phát hành độc lập thành thư viện.
- Module chỉ phục vụ build hoặc kiểm thử.
- Module hoặc dependency chỉ được bật trong một profile hay môi trường cụ thể.

Một module dùng Java mới hơn có thể nâng mức tối thiểu của toàn bộ sản phẩm nếu nó luôn được đóng gói hoặc nạp trong cùng tiến trình. Nếu module là tuỳ chọn và không có trong một cấu hình triển khai nhất định, hãy ghi rõ mức tối thiểu theo từng cấu hình.

### 2.2. Lập danh sách dependency thực sự cần ở runtime

Thu thập cả dependency trực tiếp lẫn dependency bắc cầu. Phân loại chúng theo vai trò:

| Nhóm | Ví dụ | Có thể ảnh hưởng runtime floor? |
| --- | --- | --- |
| Runtime bắt buộc | Framework, logging, ORM, thư viện nghiệp vụ, JDBC driver | Có; phải xét phiên bản thấp nhất được hỗ trợ. |
| Runtime theo môi trường | Database driver, messaging client, cloud SDK, adapter | Có nếu môi trường đó nằm trong phạm vi hỗ trợ. |
| Tuỳ chọn/profile | Module báo cáo, plugin tích hợp, connector chỉ bật ở một profile | Có trong cấu hình bật thành phần đó; có thể cần runtime floor riêng theo profile. |
| Build-time | Compiler plugin, code generator, annotation processor | Thường ảnh hưởng build JDK; có thể ảnh hưởng artifact nếu mã được sinh ra phụ thuộc API mới. |
| Test-only | JUnit, test framework, mock server, test container | Thường ảnh hưởng test JDK; không nhất thiết quyết định runtime production. |
| Vận hành | Java agent, profiler, monitoring agent, security agent | Có thể ảnh hưởng runtime nếu được nạp trong production. |

Không bỏ qua dependency bắc cầu. Ứng dụng có thể không gọi trực tiếp một thư viện, nhưng framework hoặc thư viện khác vẫn nạp và thực thi nó trong runtime.

### 2.3. Xác định môi trường thực tế

Ghi lại các thành phần ngoài mã nguồn Java:

- JDK distribution và phiên bản đang dùng trong từng môi trường.
- Container image hoặc máy chủ triển khai.
- Application server hoặc servlet container.
- Java agent, thư viện JNI và thư viện native.
- Hệ điều hành, kiến trúc CPU và các gói hệ thống liên quan.
- Các tuỳ chọn JVM, biến môi trường, system properties và cấu hình bảo mật.

Một thư viện có thể hỗ trợ Java 11 nhưng agent giám sát hoặc application server đang dùng lại yêu cầu Java 17. Mức tối thiểu của ứng dụng triển khai phải tính cả các thành phần bắt buộc này.

## 3. Thu thập bằng chứng về yêu cầu Java

Không có một nguồn duy nhất luôn thể hiện đầy đủ phiên bản Java tối thiểu. Nên kết hợp tài liệu chính thức, metadata artifact, cấu hình build, phân tích bytecode và kiểm thử trên runtime.

### 3.1. Tài liệu tương thích của nhà cung cấp

Đối với framework, application server, driver và thư viện quan trọng, tìm các tài liệu sau:

- System requirements hoặc prerequisites.
- Supported Java versions hoặc compatibility matrix.
- Release notes của đúng phiên bản đang sử dụng và phiên bản dự kiến nâng.
- Migration guide và thông tin về phiên bản dependency tối thiểu.
- Chính sách hỗ trợ, bảo trì và thời gian kết thúc hỗ trợ.

Ưu tiên tài liệu chính thức của đúng nhà cung cấp và đúng phiên bản artifact. Một bài hướng dẫn cũ hoặc câu trả lời trên diễn đàn có thể giúp tìm hướng điều tra, nhưng không đủ để xác lập cam kết hỗ trợ.

Khi ghi nhận, lưu URL hoặc tên tài liệu, phiên bản thư viện, ngày kiểm tra và câu kết luận liên quan. Nếu tài liệu chỉ nói “được kiểm thử trên Java 17” mà không tuyên bố các phiên bản thấp hơn không được hỗ trợ, đừng tự suy diễn phạm vi hỗ trợ.

### 3.2. Metadata trong Maven POM

Mở POM của artifact hoặc POM được công bố cùng thư viện. Có thể gặp các thuộc tính như:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
```

Các thuộc tính compiler cho biết cách dự án khai báo biên dịch. Chúng là bằng chứng hữu ích nhưng không phải lúc nào cũng là cam kết runtime hoàn chỉnh. POM có thể không công bố thuộc tính này, có thể kế thừa cấu hình từ parent hoặc có thể dùng một plugin được cấu hình riêng.

Đặc biệt, `source` và `target` không giới hạn đầy đủ API Java mà mã nguồn có thể gọi. Một dự án biên dịch với JDK mới nhưng đặt `target` thấp vẫn có thể vô tình gọi API chỉ xuất hiện ở JDK mới hơn. Khi có thể, dùng cấu hình `release` để kiểm soát cả mức ngôn ngữ, bytecode và API nền tảng.

### 3.3. Metadata trong Gradle

Kiểm tra `build.gradle`, `build.gradle.kts`, cấu hình convention plugin và metadata mà thư viện công bố. Ví dụ:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

Trong ví dụ này, toolchain chọn JDK 21 cho compiler, còn `options.release` đặt mục tiêu API và bytecode Java 17. Cấu hình thực tế có thể nằm trong plugin dùng chung hoặc được áp dụng theo từng subproject, vì vậy cần kiểm tra cấu hình hiệu lực chứ không chỉ một file build ở thư mục gốc.

Gradle Module Metadata có thể chứa thuộc tính `org.gradle.jvm.version` cho variant được công bố. Thuộc tính này hữu ích khi kiểm tra mức JVM mà variant yêu cầu. Tuy nhiên, không phải mọi thư viện đều công bố Gradle metadata; hãy kiểm tra thêm POM, tài liệu và artifact thực tế.

### 3.4. Manifest và cấu trúc JAR

Manifest của JAR có thể chứa thông tin như `Build-Jdk`, `Created-By` hoặc thông tin triển khai khác. Đây là dấu vết về môi trường đã tạo artifact, không phải bằng chứng chắc chắn về runtime tối thiểu.

Đối với JAR nhiều phiên bản (multi-release JAR), cùng một artifact có thể chứa các class khác nhau cho các phiên bản Java khác nhau dưới thư mục `META-INF/versions/`. JVM chọn phần class phù hợp theo phiên bản runtime. Khi phân tích, cần xét đúng phần class mà runtime đích sẽ nạp; không nên kết luận chỉ từ một class được lấy ra tuỳ ý.

### 3.5. Phiên bản bytecode của class file

Mỗi class file có major version thể hiện phiên bản định dạng bytecode. Có thể kiểm tra bằng `javap`:

```bash
javap -verbose -classpath path/to/library.jar com.example.SomeClass
```

Trong kết quả, tìm dòng `major version`. Một số giá trị thường gặp:

| Java release | Class file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Nếu một class bắt buộc có major version cao hơn mức JVM hỗ trợ, JVM cũ sẽ không nạp được class đó và thường phát sinh `UnsupportedClassVersionError`.

Tuy nhiên, bytecode version chỉ cho biết một giới hạn quan trọng, không chứng minh toàn bộ tương thích. Class có thể được biên dịch thành bytecode Java 8 nhưng vẫn tham chiếu API chỉ có từ Java 11 nếu quá trình biên dịch không được giới hạn API đúng cách. Vì vậy, cần kết hợp kiểm tra class file với kiểm tra API và tài liệu hỗ trợ.

### 3.6. Phân tích dependency và API bằng công cụ JDK

`jdeps` giúp xem dependency ở mức class/package và tìm một số phụ thuộc vào API nội bộ của JDK:

```bash
# Tìm phụ thuộc vào API nội bộ của JDK
jdeps --recursive --jdk-internals path/to/application.jar

# Phân tích JAR nhiều phiên bản theo release cần xem
jdeps --multi-release 17 --recursive path/to/library.jar
```

`jdeprscan` hỗ trợ tìm các API deprecated được tham chiếu trong class file:

```bash
jdeprscan --release 17 path/to/application.jar
```

Thay đường dẫn và release bằng giá trị phù hợp với dự án và JDK đang dùng. Xem `--help` hoặc tài liệu của chính bộ công cụ trước khi tự động hoá các lệnh này, vì khả năng hỗ trợ release phụ thuộc phiên bản JDK.

Các công cụ phân tích tĩnh có giới hạn. Chúng có thể không phát hiện đầy đủ lời gọi được tạo qua reflection, tên class được nạp động, service loading, mã native, cấu hình bên ngoài hoặc hành vi chỉ xuất hiện trong một luồng nghiệp vụ. Kết quả không có cảnh báo không đồng nghĩa đã chứng minh ứng dụng tương thích.

## 4. Xác định mức Java tối thiểu của mã nguồn ứng dụng

Sau khi khảo sát dependency, cần xác định mã nguồn của chính ứng dụng yêu cầu API và tính năng từ phiên bản nào.

### 4.1. Kiểm tra cấu hình compiler hiệu lực

Với Maven, kiểm tra:

- Property `maven.compiler.release`, `maven.compiler.source` và `maven.compiler.target`.
- Cấu hình `maven-compiler-plugin` trong POM hiện tại và parent POM.
- Profile Maven có thể thay đổi compiler release.
- Module có cấu hình riêng hoặc dùng plugin compiler khác.

Ví dụ cấu hình release:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Với Gradle, kiểm tra:

- Java toolchain được chọn cho từng project.
- `options.release` của các task `JavaCompile`.
- `sourceCompatibility` và `targetCompatibility`.
- Convention plugin, script dùng chung và cấu hình theo task.

Không chỉ đọc giá trị trong file; hãy xác nhận cấu hình nào thực sự được áp dụng cho module tạo artifact cần khảo sát.

### 4.2. Phân biệt `source`, `target` và `release`

- `source` xác định mức cú pháp/ngôn ngữ Java mà compiler chấp nhận.
- `target` xác định định dạng bytecode đầu ra.
- `release` ràng buộc mức ngôn ngữ, định dạng class file và tập API nền tảng tương ứng với release được chọn.

Nếu chỉ đặt `source` và `target`, compiler có thể vẫn nhìn thấy API của JDK đang chạy. Điều đó tạo ra tình huống mã biên dịch được nhưng gọi API không tồn tại trên runtime thấp hơn. Dùng `--release` hoặc cấu hình tương đương thường là cách rõ ràng hơn để tạo artifact hướng đến một phiên bản Java cụ thể.

### 4.3. Tìm API chỉ có ở phiên bản Java mới

Đối chiếu các API mà mã nguồn sử dụng với tài liệu API của phiên bản mục tiêu. Tập trung vào:

- Class, interface, method và field mới được thêm trong các release gần đây.
- API đã deprecated hoặc bị loại bỏ.
- Reflection, module access và truy cập package nội bộ.
- API về I/O, networking, security, process, concurrency và serialization.
- API được gọi gián tiếp qua framework hoặc thư viện hỗ trợ.

Một số đoạn mã có thể biên dịch với release thấp hơn nhưng nạp class hoặc gọi API mới thông qua reflection. Vì vậy, kiểm tra mã nguồn cần kết hợp tìm kiếm, phân tích dependency và kiểm thử trên runtime thấp nhất dự kiến hỗ trợ.

## 5. Xác định mức Java tối thiểu của từng thư viện

Với mỗi dependency bắt buộc, xác định mức Java tối thiểu của đúng phiên bản sẽ sử dụng. Không lấy mức Java của phiên bản mới nhất để kết luận cho phiên bản đang có, và không lấy mức Java của một dependency khác cùng nhà cung cấp.

### 5.1. Kiểm tra từng dependency trực tiếp

Với mỗi thư viện, ghi lại:

- Tên artifact và phiên bản chính xác.
- Vai trò và vị trí được sử dụng.
- Phạm vi: compile, runtime, provided, optional hoặc test.
- Phiên bản Java tối thiểu theo tài liệu chính thức.
- Bằng chứng từ POM, Gradle metadata hoặc class file.
- Phiên bản thay thế nếu bản hiện tại không đáp ứng yêu cầu.

### 5.2. Lần theo dependency bắc cầu

Một thư viện trực tiếp có thể yêu cầu Java 8 nhưng một dependency bắc cầu của nó lại yêu cầu Java 17. Khi đó, mức tối thiểu của nhánh dependency là Java 17 nếu dependency đó thực sự được nạp trong cấu hình đang xét.

Với Maven, có thể xem cây dependency:

```bash
mvn dependency:tree
```

Với Gradle, có thể xem dependency theo configuration:

```bash
./gradlew dependencies
```

Chú ý chọn đúng configuration như `runtimeClasspath`, `compileClasspath` hoặc configuration của test. Một cây dependency test-only không đại diện cho toàn bộ runtime production; ngược lại, chỉ xem compile classpath có thể bỏ sót thành phần chỉ được nạp lúc chạy.

### 5.3. Xử lý dependency tuỳ chọn và profile

Nếu dependency chỉ được dùng trong một profile, plugin hoặc môi trường cụ thể, hãy tính mức Java cho từng cấu hình. Ví dụ:

| Cấu hình | Dependency bổ sung | Mức Java tối thiểu giả định |
| --- | --- | --- |
| Core service | Các thư viện runtime cốt lõi | Java 11 |
| Core + reporting | Thêm thư viện báo cáo yêu cầu Java 17 | Java 17 |
| Core + legacy connector | Connector cũ vẫn hỗ trợ Java 11 | Java 11 |

Các con số trong bảng chỉ minh hoạ cách phân tích. Dự án thực tế phải dùng bằng chứng của đúng phiên bản artifact. Nếu tổ chức tuyên bố hỗ trợ toàn bộ profile trong cùng một sản phẩm, mức công bố chung phải đáp ứng profile có yêu cầu cao nhất. Nếu công bố riêng từng cấu hình, phải ghi rõ điều kiện áp dụng.

## 6. Tính phiên bản Java tối thiểu của toàn ứng dụng

Sau khi thu thập các ràng buộc, xác định tập thành phần bắt buộc trong mỗi cấu hình triển khai. Runtime floor của cấu hình đó phải đáp ứng yêu cầu cao nhất trong tập thành phần.

Có thể biểu diễn như sau:

\[
J_{min}(profile) = \max(J_{app}, J_{dependency}, J_{framework}, J_{server}, J_{agent}, \ldots)
\]

Trong đó mỗi giá trị là phiên bản Java tối thiểu được xác minh cho thành phần tương ứng. Chỉ đưa vào phép tính các thành phần thực sự cần thiết trong profile đang xét; không dùng phiên bản của công cụ build thay cho runtime requirement.

### 6.1. Ví dụ tính mức tối thiểu

Giả sử một service có các yêu cầu đã được xác minh như sau:

| Thành phần | Java tối thiểu |
| --- | ---: |
| Mã nguồn ứng dụng | 11 |
| Framework web | 17 |
| ORM và database driver | 11 |
| Thư viện xử lý nghiệp vụ | 8 |
| Application server | 17 |
| Monitoring agent bắt buộc | 17 |

Mức tối thiểu của service là Java 17 vì framework, application server và agent đều yêu cầu ít nhất phiên bản đó. Việc một số thư viện vẫn hỗ trợ Java 8 hoặc Java 11 không làm giảm mức tối thiểu chung.

Giả sử pipeline build dùng JDK 21 và compiler release 17. Kết luận cần ghi riêng: build chạy bằng JDK 21; artifact được biên dịch cho Java 17; runtime tối thiểu được hỗ trợ là Java 17. Không nên ghi đơn giản “dự án dùng Java 21” vì câu đó không thể hiện đầy đủ hợp đồng tương thích.

### 6.2. Tách mức kỹ thuật và mức cam kết sản phẩm

Sau phép tính, đối chiếu kết quả với chính sách hỗ trợ của tổ chức và nhà cung cấp. Nếu ứng dụng có thể chạy trên Java 17 nhưng chỉ có kiểm thử, bản vá và hỗ trợ production từ Java 21, thì mức cam kết sản phẩm nên là Java 21.

Nên lưu ít nhất hai kết luận:

- **Technical minimum:** mức thấp nhất có bằng chứng cho thấy tổ hợp mã nguồn, dependency và runtime có thể hoạt động.
- **Supported minimum:** mức thấp nhất mà nhóm phát triển và vận hành cam kết kiểm thử, sửa lỗi và hỗ trợ.

Hai mức này có thể trùng nhau hoặc khác nhau. Không hạ mức công bố chỉ vì một lần chạy thử thành công trên runtime cũ.

## 7. Xác minh kết luận bằng build và runtime thực tế

Phân tích tài liệu và metadata tạo ra giả thuyết có căn cứ. Để xác nhận mức tối thiểu, cần kiểm thử trên đúng JDK đó và trong môi trường đại diện cho triển khai.

### 7.1. Kiểm tra JDK đang được sử dụng

Chạy các lệnh trong môi trường build và môi trường chạy:

```bash
java -version
javac -version
mvn -version
./gradlew --version
```

Trên Windows, có thể dùng `gradlew.bat --version`. Các lệnh phải được chạy trong đúng terminal, container hoặc CI runner. `java`, `javac`, Maven và Gradle có thể trỏ đến các JDK khác nhau nếu `PATH`, `JAVA_HOME`, toolchain hoặc cấu hình daemon không thống nhất.

### 7.2. Chạy trên phiên bản thấp nhất dự kiến hỗ trợ

Chuẩn bị môi trường sạch với JDK ở mức tối thiểu đã tính. Chạy:

- Build artifact theo cấu hình đã công bố.
- Unit test và integration test phù hợp.
- Kiểm tra khởi động, nạp class và kết nối dịch vụ ngoài.
- Các luồng nghiệp vụ quan trọng.
- Kiểm thử bảo mật, TLS, serialization và xử lý dữ liệu nếu có liên quan.
- Kiểm tra agent, logging, monitoring và shutdown.

Không chỉ chạy ứng dụng bằng một lệnh `java -jar` nếu production thực tế dùng application server, container, agent hoặc cấu hình JVM riêng. Môi trường kiểm thử cần đại diện cho cách ứng dụng sẽ được triển khai.

### 7.3. Kiểm thử cả phiên bản thấp nhất và phiên bản mục tiêu

Nếu sản phẩm công bố hỗ trợ nhiều Java release, tạo ma trận kiểm thử. Ví dụ:

| JDK | Mục đích | Kết quả cần lưu |
| --- | --- | --- |
| JDK thấp nhất được hỗ trợ | Xác nhận runtime floor | Build/test hoặc chạy artifact, log khởi động, kết quả nghiệp vụ |
| JDK mục tiêu migration | Xác nhận môi trường đích | Build/test đầy đủ, cảnh báo, hiệu năng và kết quả tích hợp |
| JDK cao hơn nếu nằm trong phạm vi hỗ trợ | Phát hiện vấn đề tương thích về sau | Kết quả kiểm thử theo chính sách hỗ trợ |

Nếu build chỉ chạy trên JDK mới, vẫn cần có bước chạy artifact trên runtime thấp nhất. Ngược lại, nếu test chạy trên JDK thấp nhất nhưng artifact được build bằng compiler không giới hạn API, kết quả đó chưa thay thế được việc kiểm tra cấu hình `release` và dependency.

## 8. Mẫu bảng ghi nhận kết quả khảo sát

Nên duy trì một bảng để người khác có thể xem lại cách đưa ra kết luận. Mẫu sau có thể được sao chép vào tài liệu migration hoặc bảng kiểm kê dependency.

| Thành phần | Phiên bản đang dùng | Vai trò/phạm vi | Java tối thiểu | Nguồn bằng chứng | Trạng thái |
| --- | --- | --- | ---: | --- | --- |
| Ứng dụng/service | Ghi phiên bản artifact | Runtime | Ghi kết quả phân tích mã nguồn | Compiler release, API scan, runtime test | Đã xác minh / cần kiểm tra |
| Framework | Ghi phiên bản | Runtime bắt buộc | Theo compatibility matrix | Tài liệu nhà cung cấp | Đã xác minh / cần kiểm tra |
| Thư viện A | Ghi phiên bản | Runtime trực tiếp | Theo tài liệu và artifact | Release notes, metadata, bytecode | Đã xác minh / cần kiểm tra |
| Thư viện B | Ghi phiên bản | Dependency bắc cầu | Theo tài liệu và artifact | Dependency tree, metadata | Đã xác minh / cần kiểm tra |
| Build plugin | Ghi phiên bản | Build-time | JDK chạy build | Tài liệu plugin | Đã xác minh / cần kiểm tra |
| Application server | Ghi phiên bản | Runtime | Theo ma trận hỗ trợ | Tài liệu máy chủ | Đã xác minh / cần kiểm tra |
| Java agent | Ghi phiên bản | Production runtime | Theo tài liệu agent | Tài liệu nhà cung cấp và test | Đã xác minh / cần kiểm tra |

Ở cấp ứng dụng, ghi thêm:

| Trường | Giá trị cần ghi |
| --- | --- |
| Đơn vị triển khai | Tên service, module hoặc artifact |
| Build JDK | Phiên bản JDK chạy quy trình build |
| Compile release | Giá trị `release` hoặc cấu hình tương đương |
| Technical minimum | Phiên bản runtime thấp nhất đã phân tích và xác minh |
| Supported minimum | Phiên bản thấp nhất được cam kết hỗ trợ |
| Phiên bản migration đích | Phiên bản Java đang hướng tới |
| Cấu hình áp dụng | Profile, môi trường và dependency tuỳ chọn liên quan |
| Bằng chứng | Link tài liệu, log, báo cáo scan và kết quả test |
| Người xác nhận/ngày xác nhận | Chủ sở hữu kết luận và ngày kiểm tra |

## 9. Những sai lầm thường gặp khi xác định minimum Java version

### Chỉ dựa vào JDK trên máy lập trình viên

JDK cài trên máy có thể mới hơn nhiều so với runtime production. Nó cũng có thể khác JDK mà CI hoặc container sử dụng. Hãy thu thập thông tin từ mọi môi trường có liên quan.

### Đồng nhất build JDK với runtime JDK

Build bằng JDK 21 không nhất thiết buộc ứng dụng chạy bằng Java 21. Ngược lại, build bằng JDK cũ cũng không chứng minh dependency hỗ trợ runtime đó. Ghi riêng build JDK, compile release và runtime floor.

### Chỉ xem `sourceCompatibility` hoặc `targetCompatibility`

Hai thuộc tính này không đảm bảo mã nguồn chỉ gọi API có trong phiên bản mục tiêu. Ưu tiên `--release` hoặc cấu hình tương đương, đồng thời kiểm tra dependency và mã được nạp động.

### Chỉ xem dependency trực tiếp

Dependency bắc cầu, plugin runtime, agent và driver có thể đặt ra yêu cầu cao hơn. Cần xem đúng runtime dependency graph và cấu hình triển khai.

### Dựa vào major version của một class

Major version cao cho thấy runtime cũ có thể không nạp được class. Major version thấp không chứng minh API được dùng đều tồn tại trên runtime đó. Phải kết hợp bytecode, API, tài liệu và kiểm thử.

### Xem metadata như một cam kết đầy đủ

POM hoặc manifest có thể thiếu, cũ hoặc chỉ mô tả cách build. Hãy xác nhận với tài liệu chính thức và phiên bản artifact cụ thể.

### Coi một lần chạy thử là cam kết hỗ trợ

Một lần chạy thành công không chứng minh mọi profile, workload, hệ điều hành hoặc cấu hình production đều được hỗ trợ. Cam kết hỗ trợ cần có ma trận kiểm thử, phạm vi rõ ràng và quy trình xử lý lỗi.

## 10. Quy trình thực hiện trong giai đoạn khảo sát hệ thống

Có thể áp dụng quy trình tuần tự sau cho mỗi service hoặc artifact:

1. **Chốt phạm vi:** xác định artifact, module, profile, môi trường và các thành phần bắt buộc.
2. **Ghi nhận hiện trạng:** thu thập JDK build/runtime, compiler release, framework, dependency, server và agent.
3. **Lập dependency graph:** bao gồm dependency trực tiếp, bắc cầu, runtime, optional và test.
4. **Thu thập bằng chứng:** đọc compatibility matrix, release notes, metadata và thông tin bytecode của đúng phiên bản.
5. **Phân tích mã nguồn:** kiểm tra compiler release, API Java, reflection, module access và các điểm nạp động.
6. **Tính runtime floor:** lấy yêu cầu cao nhất trong các thành phần bắt buộc cho từng profile.
7. **Xác định mức cam kết:** đối chiếu với chính sách hỗ trợ và phạm vi kiểm thử của tổ chức.
8. **Xác minh:** build và chạy trên runtime thấp nhất dự kiến hỗ trợ, sau đó kiểm thử trên JDK migration đích.
9. **Ghi quyết định:** lưu kết quả, nguồn bằng chứng, các giả định và những điểm chưa xác minh.

Đầu ra của giai đoạn khảo sát nên là một kết luận có thể kiểm tra, chẳng hạn: “Service A dùng JDK 21 để build, biên dịch theo release 17, yêu cầu runtime tối thiểu Java 17 do framework và application server; Java 17 và Java 21 nằm trong ma trận kiểm thử hỗ trợ.” Chỉ ghi kết luận như vậy khi các chi tiết đều có bằng chứng thực tế.

## 11. Checklist hoàn thành khảo sát

- [ ] Đã xác định rõ từng service, artifact, module và profile cần hỗ trợ.
- [ ] Đã ghi riêng build JDK, compile release, test JDK và runtime JDK.
- [ ] Đã kiểm kê dependency trực tiếp, bắc cầu, runtime, optional, framework, server và agent.
- [ ] Đã tra tài liệu hỗ trợ của đúng phiên bản dependency quan trọng.
- [ ] Đã kiểm tra cấu hình compiler hiệu lực trong Maven/Gradle và các module liên quan.
- [ ] Đã phân tích bytecode, API nền tảng và các điểm sử dụng reflection hoặc nạp class động khi phù hợp.
- [ ] Đã tính runtime floor cho từng cấu hình triển khai.
- [ ] Đã phân biệt mức tương thích kỹ thuật với mức hỗ trợ chính thức.
- [ ] Đã kiểm thử trên runtime thấp nhất dự kiến hỗ trợ và lưu bằng chứng.
- [ ] Đã ghi rõ phiên bản Java migration đích, các giả định và những điểm chưa xác minh.

Khi hoàn thành khảo sát, nhóm phát triển có thể dùng runtime floor và supported minimum làm đầu vào cho quyết định nâng JDK, nâng dependency, điều chỉnh môi trường triển khai và thiết kế ma trận kiểm thử. Nếu chưa xác minh được yêu cầu của một thành phần bắt buộc, hãy giữ trạng thái chưa xác minh và tiếp tục điều tra trước khi công bố mức Java tối thiểu của toàn ứng dụng.
