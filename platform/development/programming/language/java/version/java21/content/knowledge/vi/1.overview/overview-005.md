# Xác định yêu cầu tương thích khi ứng dụng vẫn chạy trên Java 21

Trong module `JAVA_VERSION_JAVA21` (Java 21), việc tiếp tục vận hành ứng dụng trên Java 21 cần được xem như một yêu cầu kỹ thuật có thể kiểm chứng. Một ứng dụng chỉ được coi là tương thích khi mã nguồn, bytecode, thư viện, công cụ đóng gói và môi trường triển khai đều hoạt động đúng trên runtime Java 21 đã chọn.

Java 21 là một bản phát hành LTS. Tuy nhiên, thời gian cung cấp bản vá bảo mật và hỗ trợ kỹ thuật phụ thuộc vào nhà cung cấp JDK và gói hỗ trợ đang sử dụng. Vì vậy, yêu cầu tương thích cần ghi rõ phiên bản Java tối thiểu, bản phân phối JDK, mức cập nhật, hệ điều hành và kiến trúc triển khai. Không nên chỉ ghi chung chung rằng ứng dụng “chạy trên Java 21”.

## 1. Xác định Java 21 là mốc runtime tối thiểu

Trước khi thay đổi mã nguồn hoặc nâng cấp thư viện, hãy xác định chính xác môi trường mà ứng dụng phải hỗ trợ:

- **Runtime tối thiểu:** Java 21 có phải là phiên bản thấp nhất mà ứng dụng phải chạy được hay không? Nếu có, mọi thành phần được đóng gói cùng ứng dụng phải tương thích với mốc này.
- **Bản phân phối JDK:** ghi lại nhà cung cấp và bản phân phối đang dùng, chẳng hạn bản OpenJDK từ nhà cung cấp đã được tổ chức lựa chọn. Các bản phân phối cùng phiên bản Java thường có mức tương thích API cao, nhưng vẫn có thể khác về lịch cập nhật, chứng thư, cấu hình và hỗ trợ nền tảng.
- **Mức cập nhật:** xác định bản cập nhật Java 21 được phê duyệt trong môi trường phát triển, kiểm thử và sản xuất. Ưu tiên bản cập nhật bảo mật còn được nhà cung cấp hỗ trợ.
- **Nền tảng triển khai:** xác định hệ điều hành, kiến trúc CPU, môi trường container hoặc máy chủ ứng dụng, cùng các thư viện native mà ứng dụng cần.
- **Cấu hình JVM:** ghi nhận các tham số khởi động, giới hạn bộ nhớ, cấu hình TLS, truststore, locale, timezone và các Java agent đang được sử dụng.

Phân biệt JDK dùng để biên dịch với JVM dùng để chạy ứng dụng. Máy phát triển có thể cài nhiều JDK, còn container hoặc máy chủ sản xuất có thể dùng một bản phân phối khác. Việc biên dịch thành công trên máy phát triển chưa chứng minh ứng dụng chạy được trong môi trường sản xuất.

## 2. Khóa mức ngôn ngữ, API và bytecode ở Java 21

Khi Java 21 là runtime tối thiểu, mã nguồn phải được biên dịch theo mức phát hành 21. Cách thiết lập nên đồng thời kiểm soát cú pháp ngôn ngữ, API nền tảng và định dạng bytecode.

### Dùng `--release 21`

Tùy chọn `--release` của `javac` đặt mức ngôn ngữ, mức bytecode và tập API Java được phép sử dụng theo cùng một phiên bản. Đây là cách đáng tin cậy để tránh vô tình gọi API chỉ xuất hiện ở JDK mới hơn.

```bash
javac --release 21 -d out src/com/example/Main.java
```

Trong Maven, cấu hình mức phát hành cho Maven Compiler Plugin:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Hãy kiểm tra phiên bản Maven Compiler Plugin của dự án có hỗ trợ thuộc tính `maven.compiler.release` và bảo đảm các module đều dùng cùng baseline.

Với Gradle Kotlin DSL, khai báo toolchain và mức phát hành cho các tác vụ biên dịch Java:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

Toolchain giúp chọn JDK phù hợp cho các tác vụ Java. Thiết lập `options.release` làm rõ mức API và bytecode mà mã nguồn được phép sử dụng. Với dự án nhiều module, cần kiểm tra cấu hình áp dụng cho tất cả module có mã Java, kể cả mã được sinh tự động.

Chỉ đặt mức `source` và `target` không bảo đảm mã nguồn chỉ gọi những API có trong Java 21. Vì vậy, với compiler hiện đại, hãy ưu tiên `--release` hoặc cấu hình tương đương của công cụ build.

### Kiểm tra phiên bản bytecode

Java 21 sử dụng class file major version **65**. JVM Java 21 không thể nạp class file được biên dịch cho một phiên bản Java mới hơn. Trường hợp này thường gây lỗi `UnsupportedClassVersionError` khi ứng dụng khởi động hoặc khi lớp đó được nạp lần đầu.

Có thể kiểm tra một lớp bằng `javap`:

```bash
javap -verbose com.example.Main
```

Trong kết quả, tìm dòng `major version: 65`. Đây là một kiểm tra hữu ích cho bytecode, nhưng chưa đủ để chứng minh tương thích: một thư viện vẫn có thể được biên dịch ở mức bytecode 65 nhưng gọi API không tồn tại trong Java 21 thông qua liên kết động hoặc reflection.

Nếu dùng JAR nhiều phiên bản (multi-release JAR), hãy kiểm tra cả lớp nền trong JAR và các lớp nằm dưới `META-INF/versions/`. Java 21 chọn phần triển khai phù hợp với phiên bản runtime; phần dành riêng cho phiên bản mới hơn không thay thế được yêu cầu rằng phần lớp nền phải chạy được trên Java 21.

## 3. Đánh giá toàn bộ cây phụ thuộc

Ứng dụng thường không chỉ gồm mã do nhóm phát triển viết. Các thư viện trực tiếp, thư viện bắc cầu, framework, driver, plugin, annotation processor và Java agent đều có thể đặt ra yêu cầu runtime riêng.

Với từng thành phần, cần xác minh:

1. Phiên bản đó công bố hỗ trợ Java 21 hay không; phân biệt phiên bản Java tối thiểu với các phiên bản đã được nhà cung cấp kiểm thử và hỗ trợ chính thức.
2. Bytecode được phân phối có thể được JVM Java 21 nạp hay không.
3. Thành phần có gọi API chỉ xuất hiện sau Java 21, dùng API nội bộ của JDK, hoặc yêu cầu quyền truy cập reflection đặc biệt hay không.
4. Thành phần có phụ thuộc vào thư viện native, kiến trúc CPU, hệ điều hành hoặc thư viện hệ thống cụ thể hay không.
5. Phiên bản framework và các plugin đi kèm có hỗ trợ Java 21 trong đúng cấu hình ứng dụng hay không.

Không nên chỉ kiểm tra các thư viện được khai báo trực tiếp. Hãy xem xét cây phụ thuộc đã phân giải mà bản build thực sự đóng gói, vì một thư viện bắc cầu có thể nâng mức Java tối thiểu của toàn ứng dụng.

`jdeps` có thể hỗ trợ phát hiện một số phụ thuộc vào API nội bộ của JDK:

```bash
jdeps --jdk-internals --multi-release 21 app.jar
```

Kết quả này hữu ích để tìm tham chiếu tĩnh, nhưng không phát hiện đầy đủ mọi trường hợp truy cập qua reflection hoặc hành vi được tạo ở runtime. Nếu một thư viện cần mở package nội bộ bằng tùy chọn JVM như `--add-opens`, hãy xác minh lý do, phạm vi và khả năng hỗ trợ của nhà cung cấp. Ưu tiên phiên bản thư viện sử dụng API công khai được hỗ trợ.

### Phân biệt công cụ build với sản phẩm được build

Maven, Gradle, plugin build, annotation processor và công cụ sinh mã có thể chạy trên một JDK khác với JDK đích của ứng dụng. Vì thế cần xác minh hai điều riêng biệt:

- Công cụ build và các plugin chạy ổn định trên JDK được dùng trong CI.
- Mã và tài nguyên mà quá trình build tạo ra vẫn tương thích với Java 21.

Một annotation processor chạy trên JDK mới hơn có thể sinh mã hoặc bytecode vượt quá baseline nếu dự án không kiểm soát cấu hình đầu ra. Hãy đưa mã sinh tự động vào cùng quy trình biên dịch và kiểm tra như mã nguồn thông thường.

## 4. Kiểm tra các tính năng Java và cấu hình runtime

Các API đã được phát hành chính thức trong Java 21 có thể dùng khi dự án biên dịch theo release 21. Tuy nhiên, tính năng preview có quy tắc riêng: phải bật preview khi biên dịch và khi chạy bằng đúng phiên bản Java tương ứng. Bytecode sử dụng preview của Java 21 không phải là cam kết tương thích với các bản Java tiếp theo. Với ứng dụng cần vận hành ổn định lâu dài, chỉ sử dụng preview khi có quyết định kỹ thuật rõ ràng và đã kiểm soát runtime.

Ngoài bytecode, cần rà soát cấu hình khởi động và hành vi thực tế:

- **Tham số JVM:** xác nhận mọi tùy chọn `-X` và `-XX` đang dùng được hỗ trợ trong bản phân phối Java 21 đã chọn. Kiểm tra các tham số liên quan đến bộ nhớ, garbage collector, dump lỗi và logging.
- **Bộ nhớ container:** xác minh giới hạn heap và bộ nhớ tiến trình phù hợp với giới hạn container hoặc máy chủ. Không suy ra dung lượng cần thiết chỉ từ cấu hình trên máy phát triển.
- **TLS và chứng thư:** kiểm tra phiên bản giao thức, cipher suite, truststore, chứng thư và các provider mật mã cần thiết khi kết nối tới dịch vụ bên ngoài.
- **Java agent:** kiểm tra agent giám sát, tracing, profiling hoặc công cụ instrument bytecode có phiên bản hỗ trợ Java 21. Agent có thể làm thay đổi quá trình nạp lớp dù mã ứng dụng tự nó tương thích.
- **Native code:** kiểm tra JNI/JNA và thư viện native theo đúng hệ điều hành, kiến trúc CPU và môi trường thư viện hệ thống.
- **Dịch vụ tích hợp:** kiểm tra driver cơ sở dữ liệu, message broker, máy chủ ứng dụng và framework theo ma trận hỗ trợ của từng nhà cung cấp.

Các kiểm tra này cần chạy trong môi trường gần với sản xuất. Kết quả chạy trên một JDK 21 khác hoặc trên một hệ điều hành khác không tự động chứng minh rằng tổ hợp triển khai thực tế được hỗ trợ.

## 5. Lập ma trận tương thích có thể kiểm chứng

Ghi yêu cầu thành ma trận giúp nhóm phát triển, vận hành và kiểm thử dùng chung một tiêu chí nghiệm thu.

| Thành phần | Yêu cầu cần xác nhận | Bằng chứng nên lưu |
|---|---|---|
| Runtime | Java 21 là phiên bản tối thiểu; xác định nhà cung cấp và mức cập nhật | Kết quả `java --version`, cấu hình image hoặc máy chủ |
| Biên dịch | Mã nguồn và API được giới hạn ở release 21 | Cấu hình toolchain, `--release 21`, kết quả build |
| Bytecode | Các lớp trong artifact có thể được JVM 21 nạp | Kết quả kiểm tra class file và kiểm thử trên Java 21 |
| Thư viện | Toàn bộ phụ thuộc trực tiếp và bắc cầu hỗ trợ Java 21 | Dependency tree, tài liệu hỗ trợ của nhà cung cấp |
| Build | Build tool, plugin và processor chạy được trong CI | Phiên bản Maven/Gradle, JDK chạy build và log CI |
| Runtime phụ trợ | Agent, driver và thư viện native phù hợp môi trường | Danh sách phiên bản và kết quả kiểm thử tích hợp |
| Triển khai | JVM flags, bộ nhớ, TLS và cấu hình hệ thống hợp lệ | Cấu hình triển khai và kết quả smoke test |

Ma trận nên nêu rõ phạm vi được hỗ trợ. Ví dụ, “Java 21” có thể chưa đủ nếu sản phẩm chỉ được kiểm thử với một bản phân phối JDK, một kiến trúc CPU hoặc một loại container cụ thể.

## 6. Quy trình xác minh trước khi phát hành

Có thể áp dụng quy trình sau mỗi khi nâng cấp dependency, framework, plugin build hoặc thay đổi môi trường chạy:

1. **Ghi nhận baseline:** xác định bản phân phối Java 21, mức cập nhật, hệ điều hành, kiến trúc và cấu hình JVM của môi trường đích.
2. **Khóa cấu hình biên dịch:** dùng JDK toolchain phù hợp và đặt `--release 21` cho mọi module Java.
3. **Kiểm tra phụ thuộc:** phân tích cây phụ thuộc đã phân giải, xác nhận yêu cầu Java tối thiểu, bytecode, API và thư viện native của từng thành phần quan trọng.
4. **Kiểm tra artifact:** xác minh bytecode và các JAR được đóng gói; chú ý JAR nhiều phiên bản, mã sinh tự động và agent.
5. **Chạy kiểm thử trên Java 21:** thực hiện unit test, integration test và kiểm thử khởi động bằng đúng bản phân phối hoặc image dự kiến triển khai.
6. **Kiểm thử hành vi vận hành:** xác minh kết nối TLS, driver, logging, giám sát, bộ nhớ và các luồng nghiệp vụ quan trọng trong môi trường gần sản xuất.
7. **Lưu bằng chứng:** lưu cấu hình build, danh sách phiên bản, log kiểm thử và các giới hạn nền tảng đã xác nhận để lần nâng cấp sau có thể đối chiếu.

Ví dụ, nhóm phát triển có thể dùng JDK mới hơn trên máy cá nhân nhưng vẫn phải tạo artifact chạy được trên Java 21. Cấu hình `--release 21` giúp compiler giới hạn API và bytecode của mã nguồn. Sau đó, nhóm vẫn cần kiểm tra dependency tree và chạy toàn bộ kiểm thử trên Java 21, bởi compiler không thể bảo đảm rằng mọi thư viện đóng gói đều tương thích.

## 7. Nhận biết và xử lý lỗi tương thích thường gặp

| Dấu hiệu | Nguyên nhân có thể xảy ra | Hướng xác minh |
|---|---|---|
| `UnsupportedClassVersionError` | Một lớp được biên dịch cho Java mới hơn 21 | Kiểm tra class file, dependency và cấu hình compiler; biên dịch lại thành phần có mã nguồn bằng release 21 hoặc chọn phiên bản thư viện hỗ trợ Java 21 |
| `NoSuchMethodError` hoặc `NoClassDefFoundError` | API được tham chiếu không có trong runtime hoặc phiên bản thư viện thực tế khác với lúc biên dịch | Đối chiếu dependency tree, phiên bản JAR lúc chạy và API nền tảng được sử dụng |
| `IllegalAccessError` hoặc lỗi reflection | Thư viện truy cập package hoặc thành phần nội bộ không được mở | Kiểm tra phiên bản thư viện, cách instrument và tùy chọn JVM; ưu tiên bản dùng API công khai |
| Ứng dụng khởi động được nhưng lỗi khi xử lý nghiệp vụ | Thành phần chỉ được nạp khi chạy một luồng cụ thể, cấu hình runtime hoặc dịch vụ tích hợp không tương thích | Bổ sung integration test cho luồng đó trong môi trường Java 21 gần sản xuất |
| Lỗi chỉ xuất hiện trong container | Khác biệt về bản phân phối JDK, kiến trúc, chứng thư, giới hạn bộ nhớ hoặc thư viện hệ thống | Kiểm tra image thực tế, `java --version`, cấu hình JVM và các thư viện native |

Thông báo lỗi chỉ là điểm bắt đầu điều tra. Cần xác định lớp hoặc thành phần gây lỗi, phiên bản thực tế được nạp và điều kiện khiến lỗi xuất hiện trước khi kết luận nguyên nhân.

## Kết luận

Để ứng dụng tiếp tục chạy ổn định trên Java 21, hãy xem Java 21 là baseline xuyên suốt từ biên dịch đến triển khai: khóa API và bytecode bằng release 21, xác nhận mọi phụ thuộc hỗ trợ runtime này, kiểm tra cấu hình JVM và nền tảng native, rồi chạy kiểm thử trên môi trường Java 21 thực tế. Yêu cầu tương thích chỉ có giá trị khi đi kèm phiên bản cụ thể và bằng chứng kiểm thử có thể lặp lại.
