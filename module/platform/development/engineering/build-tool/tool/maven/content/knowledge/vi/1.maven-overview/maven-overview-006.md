# Quan hệ giữa biên dịch, kiểm thử, đóng gói và xuất bản trong Maven

## 1. Bức tranh tổng thể: từ mã nguồn đến artifact dùng chung

Một dự án Java không thể được phân phối chỉ bằng việc có mã nguồn chạy được trên máy lập trình viên. Maven biến mã nguồn, tài nguyên, thư viện phụ thuộc và quy tắc trong `pom.xml` thành **artifact** (sản phẩm xây dựng, thường là JAR/WAR) qua một chuỗi giai đoạn có thứ tự. Mỗi giai đoạn sử dụng kết quả hoặc kiểm tra điều kiện của các giai đoạn trước:

- **Biên dịch (compile):** chuyển `.java` thành bytecode `.class`, phát hiện lỗi cú pháp/kiểu trong mã nguồn chính.
- **Kiểm thử (test):** biên dịch và chạy kiểm thử để phát hiện hành vi sai; kiểm thử đơn vị thường chạy trước khi tạo gói.
- **Đóng gói (package):** tập hợp lớp đã biên dịch và tài nguyên thành JAR, WAR hoặc dạng khác theo `<packaging>`.
- **Xác minh (verify):** thực thi các bước kiểm tra cuối đã được cấu hình, có thể bao gồm kiểm thử tích hợp, chất lượng và tính hợp lệ của gói.
- **Cài vào kho cục bộ (install):** đưa artifact vào Maven local repository để dự án khác trên máy có thể dùng theo tọa độ Maven.
- **Xuất bản (deploy):** đưa artifact và thông tin liên quan vào **remote artifact repository** cho máy khác hoặc hệ thống CI/CD sử dụng.

Đây là mối quan hệ **phụ thuộc theo thứ tự**, không phải sáu thao tác độc lập phải gọi thủ công. Khi yêu cầu Maven chạy một phase trong lifecycle mặc định, Maven chạy những phase trước nó theo đúng thứ tự và chỉ chạy các mục tiêu plugin (goal) được gắn vào từng phase. Nếu một goal trả về lỗi, quá trình thường dừng trước khi tới các phase sau.

```text
pom.xml + src/main/java + src/main/resources
                   |
                compile           -> target/classes
                   |
       test-compile -> test       -> kết quả Surefire
                   |
                package           -> target/*.jar hoặc *.war
                   |
                verify            -> các kiểm tra cuối / Failsafe nếu cấu hình
                   |
                install           -> ~/.m2/repository (máy hiện tại)
                   |
                deploy            -> kho artifact từ xa (dùng chung)
                   |
           Quy trình triển khai riêng có thể đưa artifact lên môi trường chạy
```

**Điểm phân biệt quan trọng:** Maven `deploy` mặc định **xuất bản artifact vào kho lưu trữ**, không đồng nghĩa với triển khai ứng dụng lên máy chủ đang phục vụ người dùng. Bước triển khai runtime thường thuộc một công cụ/lệnh triển khai riêng (hoặc một plugin đã cấu hình rõ ràng).

## 2. Lifecycle quyết định thứ tự; plugin thực hiện công việc

Maven có nhiều lifecycle, nổi bật là `default`, `clean` và `site`. Chuỗi đang xét nằm trong **default lifecycle**. Các phase thường gặp theo thứ tự:

| Phase | Điều gì diễn ra | Đầu ra/ý nghĩa |
| --- | --- | --- |
| `validate` | Kiểm tra cấu hình dự án ở mức Maven | Có cơ sở để bắt đầu build |
| `process-resources` | Xử lý/sao chép tài nguyên chính (nếu có goal tương ứng) | Tài nguyên đưa vào `target/classes` |
| `compile` | Biên dịch mã nguồn chính | Các tệp `.class` |
| `process-test-resources` và `test-compile` | Chuẩn bị tài nguyên và biên dịch mã kiểm thử | `target/test-classes` |
| `test` | Chạy kiểm thử đơn vị theo cấu hình | Kết quả kiểm thử, ví dụ `target/surefire-reports` |
| `package` | Tạo gói theo kiểu packaging | `target/<artifactId>-<version>.jar` với packaging `jar` |
| `pre-integration-test`, `integration-test`, `post-integration-test` | Chuẩn bị, chạy, dọn môi trường kiểm thử tích hợp khi đã gắn goal | Kết quả kiểm thử trên thành phần tích hợp |
| `verify` | Xác minh kết quả/gói bằng các goal đã cấu hình | Một mốc kiểm tra chất lượng trước khi chia sẻ |
| `install` | Cài artifact vào local repository | Dự án trên cùng máy có thể phân giải artifact |
| `deploy` | Đẩy artifact lên remote repository đã cấu hình | Artifact sẵn sàng cho người dùng/CI khác |

Bảng lược bỏ các phase trung gian như `generate-sources` và `prepare-package`; Maven vẫn đi qua chúng theo thứ tự lifecycle. Một phase không nhất thiết tự làm việc nếu không có plugin goal nào được gắn vào nó.

Với dự án `jar`, Maven thường sử dụng các ràng buộc mặc định: `maven-compiler-plugin:compile` ở phase `compile`, `maven-compiler-plugin:testCompile` ở `test-compile`, `maven-surefire-plugin:test` ở `test`, `maven-jar-plugin:jar` ở `package`, cùng các goal của Install/Deploy Plugin ở phase tương ứng. Kiểu `war`, `pom` hoặc kiểu packaging khác có ràng buộc khác; vì vậy không được coi mọi lệnh `package` đều tạo JAR.

**Phase khác goal:** `mvn package` yêu cầu chạy mọi phase tới `package`; còn `mvn compiler:compile` gọi trực tiếp một goal và không tự có cùng bảo đảm về toàn bộ chuỗi build. Tương tự, `mvn clean package` chạy phase `clean` của lifecycle riêng trước rồi mới chạy đến `package`; chỉ `mvn package` không tự xóa kết quả build cũ.

## 3. Lệnh nào bao gồm những bước nào?

| Lệnh | Những phần chính được thực hiện | Khi nào dùng |
| --- | --- | --- |
| `mvn compile` | Chuẩn bị tài nguyên, biên dịch mã chính | Kiểm tra nhanh lỗi biên dịch; chưa chạy unit test |
| `mvn test` | Toàn bộ bước tới `test`: biên dịch mã chính, mã kiểm thử và chạy unit test | Vòng phản hồi thường xuyên khi sửa mã |
| `mvn package` | Các bước tới `package`, bao gồm `test` theo mặc định | Cần JAR/WAR để chạy thử hoặc bàn giao |
| `mvn verify` | Các bước tới `verify`, kể cả `package`; kiểm tra bổ sung nếu có cấu hình | Cổng kiểm tra trước khi chia sẻ artifact |
| `mvn install` | Tất cả bước tới `install`, bao gồm `verify` | Cho dự án khác trên cùng máy dùng artifact |
| `mvn deploy` | Tất cả bước tới `deploy`, bao gồm `install` | Công bố artifact lên repository từ xa |
| `mvn clean verify` | Dọn `target` rồi build và kiểm tra tới `verify` | Kiểm tra từ trạng thái sạch trong CI |

Ví dụ, **không cần** chạy lần lượt `mvn compile`, `mvn test`, `mvn package` rồi `mvn verify`: chỉ `mvn verify` đã bao gồm các phase phía trước. Chạy lặp các lệnh này có thể khiến mã được biên dịch và test nhiều lần không cần thiết.

Thứ tự cũng cho thấy các điều kiện chặn: lỗi biên dịch khiến test không chạy; unit test lỗi thường chặn việc đóng gói; kiểm tra ở `verify` lỗi chặn `install` và `deploy`. Đây là tính chất của một lần chạy lifecycle bình thường; nếu có cờ bỏ qua kiểm thử hoặc plugin cấu hình đặc biệt, mức bảo đảm thay đổi.

## 4. Ví dụ Java 17: nhìn thấy sản phẩm của từng bước

Tạo cấu trúc dự án:

```text
maven-phases-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/PriceCalculator.java
    └── test/java/dev/example/PriceCalculatorTest.java
```

Nội dung `pom.xml` (một dự án `jar` hoàn chỉnh, dùng Java 17 và JUnit Jupiter):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>maven-phases-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Mã chính `src/main/java/dev/example/PriceCalculator.java`:

```java
package dev.example;

public final class PriceCalculator {
    private PriceCalculator() {}

    public static int total(int unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException("Giá và số lượng phải không âm");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }

    public static void main(String[] args) {
        System.out.println(total(120, 3));
    }
}
```

Kiểm thử `src/test/java/dev/example/PriceCalculatorTest.java`:

```java
package dev.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorTest {
    @Test
    void multipliesUnitPriceAndQuantity() {
        assertEquals(360, PriceCalculator.total(120, 3));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> PriceCalculator.total(120, -1));
    }
}
```

Ở thư mục chứa `pom.xml`, với JDK 17+ và Maven đã cài:

```bash
mvn --version
mvn clean compile
java -cp target/classes dev.example.PriceCalculator
mvn test
mvn package
java -cp target/maven-phases-demo-1.0.0-SNAPSHOT.jar dev.example.PriceCalculator
mvn verify
```

Hai lệnh chạy `PriceCalculator` đều in chính xác:

```text
360
```

Giải thích kết quả:

1. Sau `mvn clean compile`, lớp `PriceCalculator.class` nằm trong `target/classes/dev/example/`. Chương trình chạy được bằng classpath này, nhưng JAR chưa được tạo.
2. Sau `mvn test`, Maven biên dịch test vào `target/test-classes`; Surefire nhận diện `PriceCalculatorTest`, chạy hai test và lưu báo cáo dưới `target/surefire-reports`.
3. Sau `mvn package`, JAR nằm ở `target/maven-phases-demo-1.0.0-SNAPSHOT.jar`. Lệnh `java -cp ... dev.example.PriceCalculator` chạy được vì lớp chính nằm trong JAR và ví dụ không cần thư viện runtime bên ngoài. Với cấu hình JAR mặc định ở đây, **không mặc định có `Main-Class` trong manifest**: `java -jar ...` sẽ không chạy theo cách trên nếu chưa cấu hình entry point.
4. Sau `mvn verify`, artifact vẫn là JAR đó, nhưng Maven đã đi qua phase `verify`. Trong ví dụ cơ bản này chưa gắn kiểm thử tích hợp hay phân tích tĩnh ở `verify`; lệnh không tự tạo thêm các cổng chất lượng chưa được khai báo.

Để tự quan sát quan hệ phụ thuộc, thử đổi giá trị mong đợi `360` trong test thành `999` rồi chạy `mvn clean package`. Unit test sẽ thất bại và lệnh dừng trước bước tạo gói; `clean` giúp tránh nhầm JAR cũ còn sót lại với kết quả của lần build lỗi. Khôi phục `360` rồi chạy `mvn clean verify` để thấy build thành công.

## 5. Kiểm thử đơn vị và kiểm thử tích hợp nằm ở đâu?

**Surefire** thường chạy unit test tại phase `test`. Với tên test mặc định như `PriceCalculatorTest`, test được thực thi trước khi đóng gói. Vì unit test chủ yếu kiểm tra logic độc lập, nó không nhất thiết cần JAR hoặc một môi trường đã triển khai.

**Failsafe** dành cho kiểm thử tích hợp, thường dùng lớp có tên `*IT.java`, `IT*.java` hoặc `*ITCase.java`. Failsafe **không được tự động gắn vào mọi dự án JAR**: cần cấu hình các goal `integration-test` và `verify`. Đoạn sau là một phần tử `<plugin>` có thể thêm vào `<build><plugins>` của POM trên:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.5.2</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Cách phối hợp này cho phép chạy kiểm thử tích hợp trong `integration-test`, thực hiện các hoạt động dọn dẹp được gắn vào `post-integration-test`, sau đó Failsafe đánh giá kết quả ở `verify`. Khi cấu hình kiểm thử tích hợp, hãy gọi **`mvn verify`**; gọi riêng `mvn integration-test` có thể bỏ qua giai đoạn dọn dẹp và xác minh. Nếu cần khởi động/dừng hệ thống phụ trợ, phải cấu hình các goal thích hợp ở `pre-integration-test` và `post-integration-test`; Maven không tự dựng cơ sở dữ liệu hay dịch vụ bên ngoài.

Sự phân chia này giải thích tại sao `mvn package` và `mvn verify` không luôn tương đương: `package` có thể tạo artifact sau unit test thành công, trong khi `verify` còn phải vượt qua các kiểm tra thực tế đã gắn ở các phase sau đóng gói.

## 6. Từ JAR trên máy đến artifact người khác dùng được

Sau `mvn install`, Maven cài artifact (và POM) vào local repository, thường ở:

```text
~/.m2/repository/dev/example/maven-phases-demo/1.0.0-SNAPSHOT/
```

Tọa độ để dự án khác phụ thuộc vào artifact là `groupId:artifactId:version`, ở đây là `dev.example:maven-phases-demo:1.0.0-SNAPSHOT`. `install` phù hợp cho phát triển cục bộ hoặc một số quy trình đa module, nhưng **máy khác không tự nhìn thấy kho local của bạn**.

`mvn deploy` chạy qua các phase trước rồi dùng Maven Deploy Plugin xuất bản artifact và POM vào remote repository (chẳng hạn Nexus hoặc Artifactory). Thông thường:

- `pom.xml` khai báo `<distributionManagement>` với `<repository>` cho bản phát hành và/hoặc `<snapshotRepository>` cho bản `-SNAPSHOT`; `<id>` xác định máy chủ kho.
- `~/.m2/settings.xml` hoặc cấu hình tương đương trên CI chứa mục `<server>` có cùng `id` để cung cấp thông tin xác thực. Không đưa mật khẩu hoặc token vào `pom.xml` hay kho mã nguồn.
- Kho từ xa cần cho phép ghi, kết nối mạng hoạt động và chính sách phiên bản phù hợp. `deploy` có thể thất bại do chưa khai báo đích, sai `id`, thiếu quyền hoặc phiên bản release đã tồn tại.

**Phân biệt ba đích đến:** `target/` chứa sản phẩm build trong workspace; `~/.m2/repository/` là kho cục bộ do `install` quản lý; remote repository là nơi `deploy` công bố sản phẩm để nhiều hệ thống truy xuất. Việc đưa artifact từ repository lên môi trường staging/production là bước triển khai ứng dụng tiếp theo, thường do CI/CD hoặc công cụ vận hành thực hiện.

## 7. Sắp xếp chuỗi này trong phát triển và CI/CD

Một cách phân chia hợp lý theo mục đích:

| Tình huống | Lệnh/cách làm | Cổng chất lượng |
| --- | --- | --- |
| Đang sửa mã Java | `mvn test` | Mã chính và test biên dịch được, unit test đạt |
| Cần sản phẩm chạy thử | `mvn clean package` | Unit test đạt rồi mới tạo gói mới |
| Pull request / kiểm tra CI | `mvn -B -ntp clean verify` | Các kiểm tra đã cấu hình tới phase `verify` đều đạt |
| Phát triển dự án phụ thuộc trên cùng máy | `mvn install` | Artifact có mặt trong local repository sau các bước trước |
| Công bố bản build được phép phát hành | `mvn -B -ntp clean deploy` với repository và credential được cấu hình | Build và verify thành công trước khi Maven xuất bản |
| Chạy bản phát hành trên môi trường đích | Lấy artifact đã xuất bản và triển khai bằng cơ chế riêng | Kiểm tra vận hành sau triển khai |

`-B` bật batch mode và `-ntp` ẩn thanh tiến trình tải, hữu ích trong log CI. Đối với bản phát hành, nên gắn phiên bản rõ ràng, bảo vệ thông tin xác thực, lưu vết artifact đã xuất bản và có chính sách không tái sử dụng cùng một phiên bản release cho nội dung khác nhau. Lệnh `deploy` có thể **build lại** mã trong lần gọi đó; đừng giả định artifact đã được verify ở một job khác chính là những byte được xuất bản nếu quy trình không kiểm soát đầu vào và đầu ra.

## 8. Các nhầm lẫn và lỗi thường gặp

1. **“`mvn compile` xong là đóng gói được.”** Compile chỉ tạo bytecode; chưa chứng minh unit test đạt và chưa tạo JAR/WAR. Muốn phân phối gói, chạy `package` hoặc phase sau.
2. **“`mvn package` không chạy kiểm thử.”** Với cấu hình JAR thông thường, phase `test` diễn ra trước `package` và Surefire chạy các test được nhận diện. Nếu bỏ qua test bằng cờ hoặc cấu hình thì kết luận này thay đổi.
3. **“`mvn verify` chắc chắn có đầy đủ unit, integration, security và coverage test.”** Maven chỉ thực hiện các goal được gắn. Nếu chưa cấu hình Failsafe, kiểm tra chất lượng hoặc coverage thì `verify` không tự sinh những bài kiểm tra ấy.
4. **“`mvn install` đã công bố thư viện cho cả nhóm.”** Install ghi vào local repository của máy đang chạy. Muốn chia sẻ qua hệ thống quản lý artifact từ xa, cần `deploy`.
5. **“`mvn deploy` đưa ứng dụng lên production.”** Deploy Plugin xuất bản artifact vào repository; triển khai runtime là công việc khác.
6. **“Chỉ cần chạy `mvn integration-test`.”** Có thể dừng trước `post-integration-test` và `verify`; với Failsafe nên chạy `mvn verify`.
7. **“Build xanh dù tắt test vẫn đáng tin như bình thường.”** `-DskipTests` thường bỏ qua chạy test (dù còn biên dịch test), còn `-Dmaven.test.skip=true` có thể bỏ qua cả biên dịch test. Chỉ dùng khi có lý do rõ ràng, không xem kết quả là đã qua cổng kiểm thử.
8. **“Thấy JAR trong `target/` nghĩa là lần build mới nhất thành công.”** JAR cũ có thể tồn tại sau lần build thất bại. Chạy `clean` khi cần chứng minh đầu ra thuộc đúng lần build.
9. **“JAR nào cũng chạy bằng `java -jar`.”** JAR thư viện thông thường không khai báo lớp `Main-Class`; cần cấu hình manifest và, nếu có phụ thuộc bên ngoài, cách đóng gói/classpath phù hợp.

## 9. Tự kiểm tra hiểu bài

- Khi chạy `mvn package`, unit test báo lỗi: liệu Maven có tiếp tục xuất bản JAR trong lần chạy bình thường không? **Không**; chuỗi dừng trước `package`.
- Sau `mvn install`, đồng nghiệp ở máy khác vẫn không lấy được thư viện: cần thay đổi điều gì? **Xuất bản qua `deploy` tới repository từ xa** và cấu hình quyền đọc repository ở phía tiêu thụ.
- Một dự án chạy `mvn verify` thành công nhưng chưa có kiểm thử tích hợp: có mâu thuẫn không? **Không**; muốn kiểm thử tích hợp thực sự phải cấu hình test và Failsafe (hoặc công cụ tương đương).
- Nếu cần vừa kiểm tra gói vừa tránh xuất bản bản lỗi, nên đặt cổng nào trước deploy? **`verify`**, với những kiểm tra thực chất đã được khai báo; `mvn deploy` tự đi qua cổng này trong cùng lifecycle.

Tài liệu gốc để tra cứu khi cần:
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Maven Deploy Plugin](https://maven.apache.org/plugins/maven-deploy-plugin/)
