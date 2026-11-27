# Không suy diễn API từ tài liệu phiên bản khác

Tài liệu Spring Modulith thường mô tả API, annotation, configuration property và hành vi theo một phiên bản cụ thể. Khi đọc tài liệu của phiên bản mới hơn phiên bản dự án đang sử dụng, bạn có thể thấy một class, method, thuộc tính annotation hoặc property chưa tồn tại trong dependency thực tế. Ngược lại, tài liệu cũ có thể bỏ qua API mới đã được bổ sung hoặc vẫn hướng dẫn cách cấu hình đã lỗi thời.

Vì vậy, không được suy diễn rằng API xuất hiện trong tài liệu đang mở chắc chắn có trong ứng dụng. Cần xác định phiên bản artifact thực tế mà build đã resolve, mở tài liệu/Javadoc/source tương ứng với phiên bản đó, kiểm tra dependency graph và xác nhận bằng compiler hoặc test phù hợp.

Trong SPRING_MODULITH_MODULE_MODEL, nguyên tắc này đặc biệt quan trọng khi sử dụng ApplicationModules, @ApplicationModule, @NamedInterface, allowedDependencies, runtime verification, event publication và các integration tùy chọn. Tên package hoặc tên tính năng giống nhau giữa hai phiên bản không bảo đảm chữ ký API, cấu hình hay semantics giống nhau.

## 1. Vì sao tài liệu phiên bản khác có thể gây lỗi?

Một thư viện tiến hóa theo thời gian. Giữa hai phiên bản, nhà phát triển có thể:

- Thêm class, method, annotation attribute hoặc enum value.
- Đổi chữ ký method, kiểu trả về, constructor hoặc generic type.
- Di chuyển class sang package hoặc artifact khác.
- Đổi tên configuration property hoặc thay đổi prefix.
- Thay đổi giá trị mặc định, điều kiện auto-configuration hoặc semantics runtime.
- Đánh dấu API deprecated rồi loại bỏ ở phiên bản major tiếp theo.
- Tách một integration thành artifact tùy chọn.
- Thay đổi yêu cầu tương thích với Spring Boot, Spring Framework hoặc Java.

Ví dụ, một trang tài liệu của bản mới có thể hướng dẫn dùng một thuộc tính annotation hoặc property mới. Nếu dự án vẫn resolve bản cũ, mã nguồn có thể không biên dịch hoặc property có thể không được bind và không tạo ra hành vi như mong đợi.

Điều nguy hiểm hơn là một số cấu hình không gây lỗi compile. Spring có thể bỏ qua một property không được nhận diện, dùng giá trị mặc định hoặc không kích hoạt auto-configuration. Ứng dụng vẫn khởi động nhưng hành vi mong muốn không xuất hiện.

## 2. Xác định phiên bản thực tế trước khi đọc API

Phiên bản ghi trong file build không phải lúc nào cũng là phiên bản cuối cùng được sử dụng. Dependency có thể được quản lý bởi BOM, dependency management, version catalog, constraint, plugin hoặc một dependency bắc cầu.

Trước khi tìm cách gọi API, xác định:

1. Phiên bản Spring Modulith mà build đã resolve.
2. Các artifact Spring Modulith đang có trên compile classpath và runtime classpath.
3. BOM hoặc dependency management nào quản lý các artifact đó.
4. Có dependency nào ghi đè phiên bản do BOM cung cấp không.
5. Test runtime có dùng tập dependency khác với production runtime không.

### Gradle

Có thể xem dependency graph của compile classpath:

~~~bash
./gradlew dependencyInsight --dependency spring-modulith-core --configuration compileClasspath
~~~

Và runtime classpath:

~~~bash
./gradlew dependencyInsight --dependency spring-modulith-runtime --configuration runtimeClasspath
~~~

Để xem các artifact Spring Modulith cùng lúc:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tên configuration có thể khác trong dự án Android, multi-project hoặc cấu hình Gradle tùy chỉnh. Hãy chọn configuration thực sự được dùng để biên dịch hoặc chạy ứng dụng.

### Maven

Xem dependency tree của các artifact thuộc group Spring Modulith:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.modulith
~~~

Kiểm tra cả dependency management và dependency tree. Một phiên bản khai báo trong property hoặc BOM không nhất thiết chứng minh artifact đó đã được resolve đúng như dự kiến nếu có override hoặc mediation từ dependency khác.

## 3. Phân biệt phiên bản BOM và phiên bản artifact

BOM quản lý một tập phiên bản dependency tương thích. Khi dự án import Spring Modulith BOM, các artifact thuộc bộ thư viện có thể được cấp phiên bản từ BOM mà không cần khai báo version riêng cho từng dependency.

Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation(platform(
        "org.springframework.modulith:spring-modulith-bom:$springModulithVersion"
    ))
    implementation("org.springframework.modulith:spring-modulith-core")
}
~~~

Ví dụ Maven:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>REPLACE_WITH_PROJECT_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là ví dụ cấu trúc quản lý phiên bản; hãy dùng phiên bản BOM được dự án chọn và xác nhận artifact thực tế có trong phiên bản đó.

Không nên trộn các artifact Spring Modulith từ nhiều release tùy ý. Ví dụ, dùng core từ một phiên bản nhưng runtime hoặc integration từ phiên bản khác có thể tạo ra lỗi binary compatibility, thiếu class hoặc auto-configuration không tương thích.

Nếu cần override một artifact riêng lẻ, hãy xác nhận lý do và kiểm tra ma trận tương thích. Một override có thể làm mất bảo đảm đồng bộ mà BOM cung cấp.

## 4. Không nhầm phiên bản Spring Boot với Spring Modulith

Spring Boot, Spring Framework, Spring Modulith và Java có chu kỳ phát hành riêng. Số phiên bản của chúng không cần giống nhau.

| Thành phần | Vai trò |
|---|---|
| Java | Phiên bản ngôn ngữ, bytecode và runtime |
| Spring Boot | Nền tảng bootstrap, auto-configuration và dependency management |
| Spring Framework | Container, transaction, event và các cơ chế nền tảng |
| Spring Modulith | Mô hình application module, verification, events và documentation |
| Integration artifact | Kết nối Spring Modulith với persistence hoặc messaging cụ thể |

Không suy luận rằng một phiên bản Spring Modulith sẽ chạy được với mọi phiên bản Spring Boot chỉ vì cả hai đều có số major gần nhau. Hãy xem compatibility information và dependency constraints của release được chọn.

Khi nâng Spring Boot hoặc Spring Modulith, xác nhận lại:

- Java baseline được hỗ trợ.
- Phiên bản Spring Framework mà Boot quản lý.
- Phiên bản Spring Modulith tương thích với nền tảng đó.
- Phiên bản integration artifact.
- Các dependency bắc cầu có bị nâng hoặc hạ ngoài dự kiến không.

## 5. Dùng tài liệu đúng phiên bản

Tài liệu có URL dạng current hoặc không chỉ rõ version có thể trỏ tới release mới nhất. Không dùng trang đó làm bằng chứng duy nhất rằng API có mặt trong dự án cũ.

Quy trình đọc tài liệu:

1. Xác định phiên bản artifact đã resolve.
2. Mở reference documentation của đúng release.
3. Chọn Javadoc của đúng artifact và version.
4. Đọc release notes giữa phiên bản đang dùng và phiên bản có ví dụ mới.
5. Kiểm tra migration guide nếu API đã đổi.
6. Đối chiếu class và method trong JAR thực tế khi còn nghi ngờ.

Nếu trang tài liệu có version selector, chọn chính xác phiên bản dự án. Nếu không tìm được tài liệu đúng phiên bản, dùng Javadoc/source JAR được phát hành cùng artifact hoặc source code tag tương ứng. Ghi rõ khoảng trống tài liệu thay vì mặc định trang current cũng đúng cho bản cũ.

### Nguồn nên ưu tiên

| Nguồn | Dùng để xác nhận điều gì? |
|---|---|
| Dependency resolution của build | Phiên bản và artifact thực tế được dùng |
| Reference documentation đúng release | Cách dùng tính năng trong phiên bản đó |
| Javadoc đúng artifact/version | Class, method, annotation attribute và chữ ký public |
| Source JAR hoặc source tag | Implementation, điều kiện và semantics khi Javadoc chưa đủ |
| Release notes | API mới, thay đổi hành vi, deprecation và bug fixes |
| Migration guide | Các bước chuyển giữa hai dòng phiên bản |
| Configuration metadata của JAR | Property được nhận diện, kiểu dữ liệu và metadata mặc định |

Một blog, câu trả lời diễn đàn hoặc ví dụ từ repository khác có thể giúp tìm hướng, nhưng phải đối chiếu lại với các nguồn của đúng release.

## 6. Kiểm tra class và method có thực sự tồn tại

Tên class trong tài liệu không đủ để kết luận class có trên classpath. Cần xác nhận:

- Artifact chứa class đã được khai báo và resolve chưa?
- Class có nằm trong package đó ở đúng version không?
- Class có phải public API hay chỉ là implementation nội bộ?
- Constructor hoặc method cần dùng có public và có chữ ký tương ứng không?
- API có bị deprecated hoặc thay thế ở phiên bản đó không?

Có thể xem nội dung JAR:

~~~bash
jar tf path/to/spring-modulith-core.jar
~~~

Nếu cần kiểm tra chữ ký class đã biên dịch, dùng javap:

~~~bash
javap -classpath path/to/spring-modulith-core.jar \
  org.springframework.modulith.core.ApplicationModules
~~~

Các lệnh này chỉ kiểm tra artifact đã resolve. Chúng không thay thế Javadoc hoặc source khi cần hiểu contract và semantics.

Nếu class không có trong JAR, hãy xác định nó thuộc artifact khác, được thêm ở release mới hơn hay đã bị di chuyển. Không tự tạo class thay thế hoặc đổi import theo phỏng đoán.

## 7. Xác minh annotation attribute và enum value

Annotation là API có thể thay đổi giữa các phiên bản. Một ví dụ dùng thuộc tính mới có thể không biên dịch với phiên bản cũ:

~~~java
@ApplicationModule(id = "inventory")
package com.example.shop.inventory;
~~~

Trước khi dùng thuộc tính id, phải xác nhận annotation ApplicationModule của đúng artifact có attribute đó. Tương tự, không suy diễn rằng một enum value, annotation target hoặc default value trong tài liệu bản mới cũng tồn tại trong bản đang dùng.

Kiểm tra:

- Tên annotation và package import.
- Attribute có tồn tại không.
- Kiểu attribute có đúng không: String, enum, array hay class.
- Giá trị mặc định là gì.
- Annotation được phép đặt ở package, type hay method.
- Attribute có thay đổi semantics giữa các release không.

Compiler giúp phát hiện attribute hoặc kiểu không tồn tại. Nhưng compiler không chứng minh default value và semantics runtime đúng như kỳ vọng. Đọc Javadoc/source đúng phiên bản và viết test cho hành vi cần thiết.

## 8. Xác minh configuration property

Configuration property có thể thay đổi tên, prefix, kiểu dữ liệu, default value hoặc điều kiện kích hoạt. Đây là nhóm API dễ bị dùng sai mà không gây compile error.

Ví dụ một tài liệu mới hướng dẫn:

~~~yaml
spring:
  modulith:
    runtime:
      verification-enabled: true
~~~

Không được giả định property này tồn tại hoặc có tác dụng trong mọi phiên bản Spring Modulith. Hãy xác nhận:

1. Phiên bản có hỗ trợ runtime verification không.
2. Artifact runtime tương ứng có trên runtime classpath không.
3. Property prefix và key đúng với phiên bản đó không.
4. Giá trị mặc định và kiểu dữ liệu là gì.
5. Auto-configuration có được kích hoạt trong môi trường hiện tại không.
6. Có điều kiện classpath, bean hoặc profile nào khác không.

### Nguồn kiểm tra property

- Reference documentation đúng release.
- Configuration metadata được đóng gói trong JAR, thường có file spring-configuration-metadata.json.
- Lớp @ConfigurationProperties và auto-configuration trong source đúng version.
- Condition evaluation report của Spring Boot khi cần chẩn đoán.

Không dùng việc ứng dụng khởi động thành công làm bằng chứng rằng property đã được nhận diện. Một property lạ có thể bị bỏ qua hoặc không kích hoạt behavior như mong muốn. Hãy kiểm tra metadata và hành vi observable.

## 9. Kiểm tra artifact tùy chọn và runtime classpath

Spring Modulith có các artifact cho core, runtime, events, documentation và tích hợp công nghệ khác. Một class hoặc tính năng có thể thuộc artifact riêng thay vì core.

Ví dụ các tình huống:

- Code compile được vì integration artifact nằm trong test classpath, nhưng production runtime không có artifact đó.
- Tài liệu của một integration giả định JPA hoặc broker adapter đã được thêm, trong khi dự án chỉ có core.
- Một auto-configuration không chạy vì dependency điều kiện chưa có.
- Dependency bị exclude hoặc scope khiến class không xuất hiện trong runtime.

Hãy kiểm tra compileClasspath, runtimeClasspath, testRuntimeClasspath và dependency scope. Đừng thêm mọi artifact chỉ để làm cho một class import được; trước hết xác định tính năng cần dùng và artifact chính thức cung cấp nó.

## 10. Compile thành công chưa đủ xác nhận API

Compiler xác nhận mã nguồn có thể liên kết với chữ ký API đang có trên compile classpath. Nó không xác nhận tất cả hành vi runtime.

Một ví dụ có thể compile nhưng vẫn sai vì:

- Property không được bind.
- Auto-configuration bị điều kiện classpath hoặc bean làm vô hiệu.
- Listener chạy ở transaction phase khác với giả định.
- Default value khác với tài liệu của phiên bản khác.
- Một API public tồn tại nhưng semantics đã thay đổi.
- Compile classpath và runtime classpath không đồng nhất.

Do đó, chọn mức xác minh theo rủi ro:

| Câu hỏi | Cách xác minh |
|---|---|
| Class/method có tồn tại? | Javadoc, JAR, javap và compile |
| Chữ ký có đúng? | Javadoc/JAR và compile probe |
| Property có được nhận diện? | Configuration metadata và binding/auto-configuration test |
| Behavior có đúng? | Unit hoặc integration test |
| Runtime artifact có đủ? | Runtime dependency graph và startup test |
| API có còn được hỗ trợ? | Javadoc, deprecation notice và release notes |

## 11. Dùng một compile probe nhỏ để xác nhận giả định

Khi không chắc một API có trong phiên bản đã resolve, tạo một test hoặc source probe nhỏ trong dự án hiện tại. Ví dụ, nếu cần xác nhận một method:

~~~java
import org.springframework.modulith.core.ApplicationModules;

class ApiAvailabilityProbe {

    void checksExpectedMethod(Class<?> applicationType) {
        ApplicationModules.of(applicationType).verify();
    }
}
~~~

Đây chỉ là ví dụ về cách compiler kiểm tra method reference; hãy thay bằng API đang cần xác minh. Compile probe nên dùng đúng module, source set và dependency configuration của ứng dụng.

Không tạo một project mẫu với dependency version mới nhất rồi kết luận API có mặt trong ứng dụng. Probe phải resolve cùng BOM, dependency constraints và artifact như dự án thực tế.

Sau khi xác nhận API compile, viết test hành vi nếu tính năng có semantics quan trọng. Đặc biệt với event, transaction, runtime verification và auto-configuration, compile thành công chưa đủ.

## 12. Đọc release notes và migration guide trước khi nâng cấp

Khi API trong tài liệu mới không có trong phiên bản hiện tại, có hai hướng:

- Dùng API tương đương được hỗ trợ ở phiên bản đang chạy.
- Lên kế hoạch nâng cấp tới phiên bản cung cấp API đó.

Không nên tự viết một bản mô phỏng API mới nếu chưa đánh giá sự khác nhau về semantics.

Trước khi nâng cấp:

1. Đọc release notes của từng mốc từ version hiện tại tới version đích.
2. Tìm các mục breaking changes, deprecations và behavior changes.
3. Đọc migration guide và compatibility requirements.
4. Xác nhận Spring Boot, Spring Framework và Java baseline.
5. Cập nhật BOM và các artifact liên quan đồng bộ.
6. Kiểm tra dependency graph sau khi resolve.
7. Biên dịch và chạy test architecture, context, integration.
8. Đánh giá cấu hình môi trường và property đã đổi.
9. Triển khai thử ở staging và quan sát behavior trước production.

Không nhảy qua release notes của phiên bản trung gian nếu dự án nâng qua nhiều major/minor release. Một thay đổi được giới thiệu ở phiên bản trung gian có thể ảnh hưởng tới cách nâng lên phiên bản đích.

## 13. Phân biệt API public, internal và API đã deprecated

Không phải mọi class có thể import đều là contract phù hợp để ứng dụng phụ thuộc lâu dài.

| Trạng thái | Cách hiểu |
|---|---|
| Public API được tài liệu hóa | Có thể sử dụng theo contract của đúng phiên bản |
| Public nhưng không được khuyến nghị | Cần đọc ghi chú ổn định và phạm vi hỗ trợ |
| Internal implementation | Không nên phụ thuộc trực tiếp dù class có thể truy cập |
| Deprecated API | Có thể vẫn tồn tại nhưng đã có cảnh báo hoặc hướng thay thế |
| API bị loại bỏ | Không thể dùng trong artifact hiện tại |
| API thuộc integration artifact | Chỉ có khi artifact tương ứng có mặt trên classpath |

Với Spring Modulith, cần phân biệt API dùng để xây dựng module model với các lớp triển khai nội bộ. Không dựa vào việc một package bắt đầu bằng tên spring.modulith hoặc class có modifier public để kết luận mọi member là contract ổn định. Hãy xem Javadoc, annotation API status nếu có, deprecation và source của đúng release.

## 14. Những ví dụ suy diễn sai thường gặp

| Suy diễn | Vì sao không an toàn | Cách xác minh |
|---|---|---|
| Tài liệu current có method thì version cũ cũng có | Method có thể mới được thêm | Javadoc và JAR đúng version |
| Annotation ở ví dụ có attribute mới thì dự án dùng được | Attribute có thể chưa tồn tại | Kiểm tra annotation type trong artifact đã resolve |
| Property trong trang mới sẽ hoạt động ở bản cũ | Property có thể chưa được bind hoặc có prefix khác | Configuration metadata và auto-configuration đúng release |
| Có core artifact là có mọi integration | Integration có thể ở artifact riêng | Dependency graph và tài liệu artifact |
| BOM version giống artifact version được khai báo | Có thể bị override hoặc mediation | Dependency insight/tree |
| Test compile được nghĩa là production chạy được | Runtime classpath có thể thiếu artifact | Kiểm tra runtimeClasspath và startup test |
| Class public là API được hỗ trợ | Có thể là internal hoặc deprecated | Javadoc, source và API status |
| Ví dụ từ blog chạy được với mọi Spring Boot | Compatibility matrix có thể khác | Kiểm tra Boot/Framework/Java requirements |

## 15. Quy trình xác minh API trước khi đưa vào code

Mỗi khi định sử dụng một API, hãy thực hiện:

1. **Ghi rõ giả định.** Xác định class, method, annotation attribute hoặc property cần dùng.
2. **Xác định phiên bản resolve.** Đọc dependency graph thay vì chỉ nhìn version variable.
3. **Xác định artifact sở hữu API.** Core, runtime hay integration.
4. **Mở nguồn đúng release.** Reference docs, Javadoc hoặc source JAR tương ứng.
5. **Đối chiếu chữ ký.** Package, visibility, parameters, return type, enum và default.
6. **Đối chiếu semantics.** Transaction, auto-configuration, default behavior và điều kiện classpath.
7. **Compile probe.** Dùng đúng project classpath để kiểm tra API thực sự liên kết được.
8. **Test hành vi.** Viết unit/context/integration test theo rủi ro.
9. **Ghi lại version.** Trong ghi chú kỹ thuật hoặc PR, nêu phiên bản artifact đã xác minh.
10. **Review khi nâng cấp.** Lặp lại quy trình khi BOM hoặc artifact version thay đổi.

Nếu chưa xác minh được một giả định, hãy đánh dấu nó là chưa xác nhận và không trình bày như một API chắc chắn tồn tại.

## 16. Ví dụ quy trình điều tra một method không tìm thấy

Giả sử code dùng một method được copy từ tài liệu mới nhưng compiler báo không tìm thấy method.

~~~text
Cannot resolve method 'someMethod(...)'
~~~

Không nên ngay lập tức đổi tên method hoặc nâng một artifact riêng. Hãy kiểm tra:

1. Dependency insight/tree cho biết phiên bản nào được resolve?
2. Có nhiều version Spring Modulith trong graph không?
3. Class chứa method có thuộc artifact đã khai báo không?
4. Javadoc của đúng version có method đó không?
5. Method có tên khác, overload khác hoặc chỉ xuất hiện ở release mới hơn không?
6. Có migration note chỉ cách thay thế API cũ không?

Nếu method chỉ có từ release mới, chọn API được hỗ trợ trong version hiện tại hoặc lên kế hoạch nâng đồng bộ BOM. Không copy implementation nội bộ của thư viện vào ứng dụng chỉ để tránh nâng cấp.

## 17. Ví dụ điều tra một property không có tác dụng

Giả sử ứng dụng khai báo một property từ tài liệu mới nhưng runtime behavior không thay đổi. Quy trình:

1. Xác nhận runtime artifact có trong runtimeClasspath.
2. Xác nhận version của artifact đó.
3. Tìm property trong configuration metadata của artifact.
4. Kiểm tra prefix, key, type và default value.
5. Xem auto-configuration condition có được thỏa mãn không.
6. Kiểm tra profile và nguồn property có ghi đè giá trị không.
7. Viết context test hoặc quan sát startup behavior để xác nhận tính năng thực sự được bật.

Đừng coi việc YAML hợp lệ hoặc ứng dụng khởi động thành công là bằng chứng property có hiệu lực. YAML parser chỉ xác nhận cú pháp, không xác nhận Spring Modulith có bind property đó.

## 18. Ghi rõ phiên bản trong ví dụ và tài liệu nội bộ

Khi viết hướng dẫn cho nhóm, tránh đưa một snippet không có ngữ cảnh version nếu API có khác biệt giữa các release.

Một ví dụ tốt nên nêu:

- Spring Modulith version hoặc version range đã kiểm tra.
- Artifact cần thiết.
- Spring Boot/Java baseline nếu có yêu cầu tương thích.
- Property mặc định và điều kiện kích hoạt.
- API thay thế nếu hướng dẫn còn hỗ trợ phiên bản cũ.

Ví dụ cách ghi:

~~~text
Ví dụ này đã được xác minh với Spring Modulith <version>
và artifact <artifact-name>. Nếu dự án dùng version khác,
hãy đối chiếu Javadoc và configuration metadata tương ứng.
~~~

Không dùng placeholder trong tài liệu cuối của dự án nếu người đọc cần một version cụ thể để copy. Hãy thay placeholder bằng version đã kiểm tra hoặc nói rõ ví dụ là minh họa.

## 19. Checklist trước khi sử dụng API Spring Modulith

- [ ] Xác định Spring Modulith version thực tế đã resolve.
- [ ] Xác nhận BOM và các artifact cùng bộ được quản lý đồng bộ.
- [ ] Kiểm tra compileClasspath, runtimeClasspath và testRuntimeClasspath.
- [ ] Xác định artifact chứa class hoặc tính năng cần dùng.
- [ ] Dùng reference documentation đúng release.
- [ ] Đối chiếu Javadoc/source của đúng artifact và version.
- [ ] Kiểm tra method signature, annotation attribute, enum và constructor.
- [ ] Kiểm tra deprecation, removal và migration note.
- [ ] Kiểm tra configuration property trong metadata và auto-configuration.
- [ ] Không giả định property mới có tác dụng trong version cũ.
- [ ] Compile probe bằng dependency graph thực tế.
- [ ] Viết test cho behavior, transaction và runtime condition cần xác nhận.
- [ ] Ghi version đã xác minh trong tài liệu hoặc pull request.
- [ ] Lặp lại việc xác minh sau khi đổi BOM hoặc nâng cấp dependency.

## 20. Kết luận

Không suy diễn API từ tài liệu phiên bản khác là nguyên tắc quan trọng khi sử dụng Spring Modulith. Tài liệu current có thể mô tả class, method, annotation attribute hoặc configuration property chưa tồn tại trong phiên bản dự án. Một ví dụ compile được ở project khác cũng không chứng minh API có mặt trong dependency graph của ứng dụng hiện tại.

Hãy bắt đầu từ phiên bản artifact thực tế đã resolve, xác định đúng artifact chứa tính năng, đối chiếu reference documentation/Javadoc/source và release notes cùng phiên bản, sau đó xác nhận bằng compile probe và test runtime phù hợp. Đặc biệt, kiểm tra riêng configuration property vì property không được nhận diện có thể không gây lỗi compile. Quản lý BOM đồng bộ, hiểu khác biệt giữa compile và runtime classpath, và ghi rõ version đã xác minh giúp tránh phụ thuộc vào API không tồn tại hoặc behavior không được hỗ trợ.

## Tài liệu tham khảo

- [Spring Modulith — Reference Documentation](https://docs.spring.io/spring-modulith/reference/)
- [Spring Modulith — API Documentation](https://docs.spring.io/spring-modulith/docs/current/api/)
- [Spring Modulith — Release Notes](https://github.com/spring-projects/spring-modulith/releases)
- [Gradle — Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
