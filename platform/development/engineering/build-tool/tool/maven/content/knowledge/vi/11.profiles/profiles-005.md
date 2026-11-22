# activeByDefault và ảnh hưởng của các profile khác trong cùng POM

## 1. Vấn đề: vì sao profile “mặc định” đột nhiên không còn hiệu lực?

Trong Maven, **build profile** là một tập thay đổi cấu hình chỉ áp dụng khi profile được kích hoạt: properties, dependencies, repositories, plugin configuration, plugin executions, build options... Một cách kích hoạt là viết `<activeByDefault>true</activeByDefault>` trong `<activation>` của profile ở `pom.xml`.

Tuy nhiên, `activeByDefault` **không có nghĩa là profile luôn hoạt động**. Maven dùng nó như một cấu hình dự phòng: nếu **không có profile khác được kích hoạt trong cùng POM**, các profile được đánh dấu `activeByDefault=true` có thể hoạt động. Khi **một profile khác trong chính POM đó** được kích hoạt rõ ràng hoặc qua điều kiện, các profile chỉ active-by-default của POM ấy bị **tự động vô hiệu hóa**.

Ví dụ nhóm định nghĩa:

- `local`: mặc định cho lập trình viên.
- `ci`: chủ động bật bằng `-Pci` khi chạy pipeline.
- `cloud`: tự bật khi có CLI property `-Dtarget.env=cloud`.

Nếu `local` là active-by-default, Maven có thể xử lý như sau:

~~~text
Không -P, không trigger khác
    -> local hoạt động

-Pci
    -> ci hoạt động; local tự tắt

-Dtarget.env=cloud
    -> cloud hoạt động; local tự tắt

-Pci -Dtarget.env=cloud
    -> ci và cloud cùng hoạt động; local tự tắt

-Plocal,ci
    -> local được bật tường minh và ci cùng hoạt động
       (không còn chỉ dựa vào activeByDefault của local)
~~~

Đây là hành vi quan trọng khi profile `local` đặt một property mà nhóm nghĩ “lúc nào cũng tồn tại”. Khi bật `ci`, property ấy có thể biến mất hoặc quay về giá trị từ POM cơ sở, và build đổi hành vi.

## 2. Cú pháp activeByDefault đúng trong pom.xml

Một profile được khai báo dưới mục `<profiles>` của POM:

~~~xml
<profiles>
    <profile>
        <id>local</id>
        <activation>
            <activeByDefault>true</activeByDefault>
        </activation>
        <properties>
            <demo.mode>local</demo.mode>
        </properties>
    </profile>
</profiles>
~~~

Đây là **mảnh POM**; phải đặt trong phần tử gốc `<project>` của `pom.xml` hợp lệ.

Giải thích từng mục:

- `<id>local</id>`: định danh profile, dùng để chọn bằng `-Plocal` hoặc vô hiệu hóa tường minh.
- `<activation>`: nhóm quy tắc xác định khi nào Maven chọn profile.
- `<activeByDefault>true</activeByDefault>`: profile là ứng viên mặc định **nếu không có profile khác được kích hoạt trong cùng POM**.
- `<properties>`: một phần tác động của profile khi đang active. Trong ví dụ, `demo.mode` được gán `local`.

Nếu không khai báo `activeByDefault`, giá trị mặc định của cờ này là `false`. Maven không tự kích hoạt profile chỉ vì nó đứng đầu file hoặc có tên `local`/`default`.

**Phân biệt với** `settings.xml`: một profile có thể được kích hoạt bằng danh sách `<activeProfiles>` trong settings, nhưng đó là cách **chủ động kích hoạt**, không phải cùng một ý nghĩa với `activeByDefault` đặt trong POM. Cách giải quyết profile ở các nguồn khác nhau cần xem theo đúng “profile container” và phiên bản Maven.

## 3. Quy tắc cốt lõi: profile khác trong cùng POM sẽ tắt activeByDefault

Giả sử chính một POM có ba profile:

~~~xml
<profiles>
    <profile>
        <id>local</id>
        <activation>
            <activeByDefault>true</activeByDefault>
        </activation>
        <properties>
            <demo.mode>local</demo.mode>
        </properties>
    </profile>

    <profile>
        <id>ci</id>
        <properties>
            <demo.mode>ci</demo.mode>
        </properties>
    </profile>

    <profile>
        <id>cloud</id>
        <activation>
            <property>
                <name>target.env</name>
                <value>cloud</value>
            </property>
        </activation>
        <properties>
            <demo.mode>cloud</demo.mode>
        </properties>
    </profile>
</profiles>
~~~

Đây cũng là một **mảnh POM**, chưa phải `pom.xml` đầy đủ. Có thể suy ra:

1. `local` chỉ active-by-default. Nếu không có profile nào khác ở POM này active, Maven dùng nó.
2. `ci` không có `<activation>`; khi chạy `mvn -Pci ...`, nó được bật **tường minh**.
3. `cloud` có activation theo property; khi Maven thấy `target.env=cloud` trong nguồn phù hợp (ví dụ CLI `-Dtarget.env=cloud`), profile này tự active.
4. Khi `ci` hoặc `cloud` active, `local` bị tắt nếu **nó chỉ được bật nhờ activeByDefault**.
5. Nếu người dùng bật lại `local` bằng `-Plocal`, nó trở thành profile **active tường minh**; có thể cùng tồn tại với `ci` hoặc `cloud`.
6. Nếu `ci` và `cloud` cùng active, Maven **gộp tác động của cả hai**; không có quy tắc “chỉ chọn duy nhất một profile”.

**Quan trọng: phạm vi “cùng POM”.** Profile ở POM con, POM cha, settings.xml hoặc module khác không mặc nhiên có cùng quan hệ loại trừ với active-by-default profile ở một POM bất kỳ. Hãy phân tích activation tại **POM khai báo profile**, rồi xem effective model kết quả; đừng tưởng mọi profile đang có trong toàn reactor đều thuộc một nhóm độc quyền duy nhất.

## 4. Bảng tình huống kích hoạt trong cùng một POM

Dùng đúng thứ tự ba profile `local`, `ci`, `cloud` ở mục 3, giả sử không có activation bổ sung từ môi trường hay settings.

| Lệnh | Profile có hiệu lực trong POM ví dụ | Lý do |
| --- | --- | --- |
| `mvn verify` | `local` | Không profile khác active; `local` được chọn mặc định. |
| `mvn -Pci verify` | `ci` | `ci` được bật tường minh; `local` auto-off. |
| `mvn -Dtarget.env=cloud verify` | `cloud` | Property kích hoạt `cloud`; `local` auto-off. |
| `mvn -Pcloud verify` | `cloud` | Chỉ định `cloud` tường minh, không cần trigger property. |
| `mvn -Pci -Dtarget.env=cloud verify` | `ci` + `cloud` | Hai nguồn activation cùng có hiệu lực; `local` auto-off. |
| `mvn -Plocal,ci verify` | `local` + `ci` | `local` được bật **tường minh**, không chỉ nhờ default. |
| `mvn -P=-local verify` | Không profile nào trong ba profile active | Cú pháp tắt `local`; giả sử không có trigger khác. |
| `mvn -Pci,cloud verify` | `ci` + `cloud` | Kích hoạt hai profile bằng danh sách CSV. |

Ở hàng `-P=-local`, các **properties cơ sở bên ngoài profile** vẫn tồn tại. “Không profile nào active” không có nghĩa Maven mất toàn bộ `pom.xml` hay mất Super POM.

Trong thực tế, profile có thể còn được bật bởi `settings.xml`, JDK, hệ điều hành, tệp hoặc property khác; vì thế trạng thái ngoài ví dụ phải được **xác minh bằng công cụ** chứ không đoán từ mỗi lệnh.

## 5. Ví dụ hoàn chỉnh chạy được bằng Maven và Java 17

Ví dụ nhỏ dưới đây cho phép nhìn thấy trực tiếp cách `activeByDefault` bị ảnh hưởng: ba profile thay đổi `demo.mode`; Maven lọc biểu thức trong resource khi build; chương trình Java 17 đọc resource đó và in kết quả.

Dự án sử dụng Maven 3.9.x tương thích, JDK 17+, Maven Compiler Plugin và Resources Plugin đã pin phiên bản. Không dùng thư viện Java bên ngoài.

Cấu trúc thư mục:

~~~text
maven-profile-default-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── org/example/ProfileApp.java
        └── resources/
            └── app.properties
~~~

### 5.1. pom.xml hoàn chỉnh

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>maven-profile-default-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <demo.mode>base</demo.mode>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>local</id>
            <activation>
                <activeByDefault>true</activeByDefault>
            </activation>
            <properties>
                <demo.mode>local</demo.mode>
            </properties>
        </profile>

        <profile>
            <id>ci</id>
            <properties>
                <demo.mode>ci</demo.mode>
            </properties>
        </profile>

        <profile>
            <id>cloud</id>
            <activation>
                <property>
                    <name>target.env</name>
                    <value>cloud</value>
                </property>
            </activation>
            <properties>
                <demo.mode>cloud</demo.mode>
            </properties>
        </profile>
    </profiles>
</project>
~~~

Trong POM này:

- `demo.mode=base` nằm ở **model cơ sở**, không thuộc profile nào. Đây là giá trị dự phòng khi `local` không active và chưa có profile khác gán lại.
- `local` có `activeByDefault=true` và đặt `demo.mode=local` khi được chọn.
- `ci` chỉ được kích hoạt tường minh bằng `-Pci` hoặc một nguồn activation thích hợp.
- `cloud` có điều kiện property `target.env=cloud`, không yêu cầu đặt `-Pcloud` nếu điều kiện đã thỏa mãn.
- Cả ba profile chỉ sửa một property dễ quan sát; không tự thực hiện deploy hoặc truy cập cloud thật.

### 5.2. Resource cần lọc: app.properties

Tạo `src/main/resources/app.properties`:

~~~properties
mode=${demo.mode}
~~~

Maven Resources Plugin với `filtering=true` sẽ thay `${demo.mode}` bằng giá trị mà Maven xác định cho lần build. Đây là **resource filtering tại build time**: chương trình Java đọc file đã được xử lý, không tự tham gia đánh giá profile.

### 5.3. Java source: ProfileApp.java

Tạo `src/main/java/org/example/ProfileApp.java`:

~~~java
package org.example;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class ProfileApp {
    private ProfileApp() {
    }

    public static void main(String[] args) throws IOException {
        Properties config = new Properties();
        try (InputStream input =
                     ProfileApp.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("app.properties not found");
            }
            config.load(new InputStreamReader(input, StandardCharsets.UTF_8));
        }
        System.out.println("mode=" + config.getProperty("mode"));
    }
}
~~~

Đây là lớp Java độc lập có `main`, tên package và đường dẫn thư mục khớp nhau; code biên dịch được với Java 17 và không dùng thư viện bên ngoài.

### 5.4. Kịch bản A: chỉ có profile mặc định

Từ thư mục chứa `pom.xml`:

~~~bash
mvn -B -ntp clean package
java -cp target/classes org.example.ProfileApp
~~~

Với môi trường không có activation khác, profile `local` active. **Stdout chính xác của riêng lệnh `java`**:

~~~text
mode=local
~~~

Lệnh Maven có log riêng; ví dụ không cố định log của Maven vì nó thay đổi theo phiên bản/plugin/cache.

### 5.5. Kịch bản B: bật profile khác bằng -P

~~~bash
mvn -B -ntp -Pci clean package
java -cp target/classes org.example.ProfileApp
~~~

`ci` được bật tường minh. `local` chỉ active-by-default nên tự bị tắt. Giá trị `demo.mode` đến từ `ci`; stdout của riêng lệnh Java:

~~~text
mode=ci
~~~

### 5.6. Kịch bản C: bật profile khác bằng property

~~~bash
mvn -B -ntp -Dtarget.env=cloud clean package
java -cp target/classes org.example.ProfileApp
~~~

`target.env=cloud` thỏa điều kiện kích hoạt `cloud`; `local` bị tắt. Stdout của lệnh Java:

~~~text
mode=cloud
~~~

Lưu ý: property `target.env` dùng để **kích hoạt profile**; nó không tự biến Maven thành công cụ triển khai cloud. Trong ví dụ chỉ có xử lý resource.

### 5.7. Kịch bản D: tắt local mà không bật profile khác

~~~bash
mvn -B -ntp -P=-local clean package
java -cp target/classes org.example.ProfileApp
~~~

Với Maven hỗ trợ cú pháp tắt profile và không có nguồn activation khác, `local` bị loại. Không profile nào trong ba profile cung cấp `demo.mode`; giá trị cơ sở `base` vẫn tồn tại. Stdout của Java:

~~~text
mode=base
~~~

`-P=-local` là cú pháp vô hiệu hóa profile `local` (dạng có `=` tránh các vấn đề parse khi value bắt đầu bằng dấu trừ). Trên Bash/Zsh cũng có thể dùng tiền tố `!` nhưng phải quote/escape vì có xử lý history; dạng `-P=-local` đơn giản hơn.

**Tại sao phải chạy `clean package` trước mỗi lệnh `java`?** Ứng dụng đọc `target/classes/app.properties` đã được Maven tạo trong lần build. Nếu chỉ thay `-P` mà không build lại, Java có thể vẫn đọc resource của lần chạy trước, dẫn đến kết luận sai về profile.

## 6. Quan sát profile đang active: help:active-profiles

Không suy đoán profile từ file XML khi có parent POM, `settings.xml` hoặc CI. Maven Help Plugin có goal:

~~~bash
mvn help:active-profiles
~~~

Kiểm tra cùng dự án mẫu:

~~~bash
mvn -Pci help:active-profiles
mvn -Dtarget.env=cloud help:active-profiles
mvn -Pci -Dtarget.env=cloud help:active-profiles
mvn -P=-local help:active-profiles
~~~

Khi không có nguồn kích hoạt khác, bạn sẽ thấy lần lượt danh sách tương ứng với `ci`, `cloud`, `ci + cloud`, hoặc không có profile trong ba profile ví dụ. Help Plugin có thể in thêm project, đường dẫn source và log tùy Maven version, nên **không khẳng định toàn bộ stdout cố định**.

Để xem một property cụ thể:

~~~bash
mvn -q -Dexpression=demo.mode -DforceStdout help:evaluate
mvn -q -Pci -Dexpression=demo.mode -DforceStdout help:evaluate
mvn -q -Dtarget.env=cloud -Dexpression=demo.mode -DforceStdout help:evaluate
~~~

Với cấu hình mẫu, các **giá trị được đánh giá** lần lượt là `local`, `ci`, `cloud`. Đây là một cách nhanh để xác nhận trước khi chạy toàn bộ lifecycle, nhưng plugin vẫn cần được tải và Maven phải resolve được POM.

Kiểm tra bản model có hiệu lực:

~~~bash
mvn -Pci help:effective-pom
mvn -Dtarget.env=cloud help:effective-pom
~~~

`help:effective-pom` là công cụ hữu ích để xem properties, plugin executions, repositories và những thay đổi sau khi áp dụng profile. Nó không thay việc chạy test thực tế: profile active chưa bảo đảm mọi plugin goal sẽ thành công.

## 7. Khi nhiều profile trong cùng POM cùng active: có phải profile bật sau sẽ thắng?

**Không thể dùng đơn giản thứ tự người dùng gõ `-P` để xác định thứ tự ưu tiên.** Maven gộp các tác động của nhiều profile active; khi cùng định nghĩa một giá trị scalar như một property và cùng nằm trong một POM, **profile được khai báo sau trong POM có thể ghi đè profile trước** đối với phần tử trùng tên.

Trong POM mẫu thứ tự khai báo là:

~~~text
1. local
2. ci
3. cloud
~~~

Các ví dụ sau giả sử không có `-Ddemo.mode=...` hay nguồn override khác.

| Cách kích hoạt | Các profile active | Kết quả của demo.mode | Giải thích |
| --- | --- | --- | --- |
| `mvn -Pci,cloud ...` | `ci` + `cloud` | `cloud` | Trong POM, `cloud` khai báo sau `ci`. |
| `mvn -Pcloud,ci ...` | `cloud` + `ci` | `cloud` | Đảo thứ tự CSV của `-P` không đảo thứ tự khai báo POM. |
| `mvn -Pci -Dtarget.env=cloud ...` | `ci` + `cloud` | `cloud` | `cloud` được kích hoạt bởi property, cùng gán `demo.mode`. |
| `mvn -Plocal,ci ...` | `local` + `ci` | `ci` | `local` được bật tường minh, nhưng `ci` đứng sau trong POM. |
| `mvn -Plocal,cloud ...` | `local` + `cloud` | `cloud` | Giá trị trùng của profile đứng sau được áp dụng. |

Ví dụ chạy:

~~~bash
mvn -B -ntp -Pci,cloud clean package
java -cp target/classes org.example.ProfileApp
~~~

Stdout của lệnh Java, khi dùng đúng POM mẫu:

~~~text
mode=cloud
~~~

**Hạn chế của quy tắc ưu tiên:** không phải mọi thứ là “profile cuối thắng toàn bộ”. Các danh sách dependency, repository, plugin, executions và cấu hình XML có quy tắc **merge** khác nhau. Một profile có thể bổ sung thành phần thay vì thay thế hoàn toàn. Khi thấy mâu thuẫn, dùng `help:effective-pom` và xem goal thật sự chạy.

Một trường hợp khác là **nhiều profile cùng `activeByDefault=true` trong cùng POM**. Nếu không có profile khác được kích hoạt, chúng có thể cùng active. Nếu chúng ghi đè cùng tên property, thứ tự trong POM sẽ ảnh hưởng kết quả. Đừng dựa vào tên `default1`/`default2` để cho rằng chỉ có một profile mặc định duy nhất.

## 8. -P và điều kiện activation khác nhau thế nào?

Có nhiều cách khiến một profile active:

| Cơ chế | Ví dụ | Điều cần nhớ |
| --- | --- | --- |
| `activeByDefault` | `<activeByDefault>true</activeByDefault>` | Dự phòng khi không có profile khác active trong cùng POM. |
| CLI `-P` | `mvn -Pci verify` | Kích hoạt profile theo id một cách tường minh. |
| CLI property | `mvn -Dtarget.env=cloud verify` | Chỉ hoạt động khi profile có `<activation><property>` phù hợp. |
| `settings.xml` activeProfiles | `<activeProfiles><activeProfile>ci</activeProfile></activeProfiles>` | Kích hoạt profile qua settings và phạm vi id tương ứng. |
| JDK | `<jdk>[17,)</jdk>` | Điều kiện khớp JDK mà Maven dùng; kiểm tra phiên bản/thứ tự ở tài liệu chính thức. |
| OS | `<os><family>Windows</family></os>` | Điều kiện phụ thuộc môi trường host. |
| File | `<file><exists>...` hoặc `<missing>...` | Điều kiện dựa trên trạng thái file tại lúc model được dựng. |

Không phải cứ viết property `target.env` trong `<properties>` của POM thì nó sẽ trở thành điều kiện kích hoạt được Maven 3 dùng ngay: việc kích hoạt profile xảy ra sớm và các giá trị dùng cho activation có giới hạn về nguồn/khả năng interpolation. Trong Maven 3, cách ổn định để minh họa property activation là truyền `-Dtarget.env=cloud` hoặc dùng nguồn system property phù hợp; **Maven 4.1 bổ sung cơ chế cascading activation** giữa các profile trong cùng POM, nên khi dùng phiên bản mới phải đọc tài liệu đúng phiên bản.

Nếu một profile có nhiều điều kiện activation cùng loại hoặc khác loại, cách kết hợp và hỗ trợ còn tùy phiên bản Maven; không tùy tiện ghép nhiều `<property>` vào một profile rồi cho rằng đó là cú pháp Maven hỗ trợ.

**Tác động quan trọng:** `activeByDefault` không phải chiến lược “luôn cộng thêm các thuộc tính chung” cho mọi profile. Khi cần bất biến, hãy đặt cấu hình chung **ngoài `<profiles>`** hoặc trong parent/pluginManagement; dùng profile cho phần biến thiên theo môi trường.

## 9. Thiết kế POM tốt: đặt baseline ngoài profile, override trong profile

Đây là mẫu thường dễ bảo trì hơn nếu bạn có cả cấu hình chung lẫn cấu hình riêng theo môi trường.

**Mẫu dễ gây bất ngờ:**

~~~xml
<profiles>
    <profile>
        <id>local</id>
        <activation>
            <activeByDefault>true</activeByDefault>
        </activation>
        <properties>
            <maven.compiler.release>17</maven.compiler.release>
            <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        </properties>
    </profile>
</profiles>
~~~

Khi chạy `-Pci` và `ci` là profile khác trong cùng POM, `local` sẽ tự tắt. Nếu `ci` không khai báo lại các thông số cần thiết, build có thể mất cấu hình Java release/encoding mong đợi.

**Mẫu an toàn hơn:**

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <demo.mode>base</demo.mode>
</properties>
<profiles>
    <profile>
        <id>local</id>
        <activation>
            <activeByDefault>true</activeByDefault>
        </activation>
        <properties>
            <demo.mode>local</demo.mode>
        </properties>
    </profile>
    <profile>
        <id>ci</id>
        <properties>
            <demo.mode>ci</demo.mode>
        </properties>
    </profile>
</profiles>
~~~

Đây là **mảnh XML** đặt trong `<project>`; nó là nguyên tắc thiết kế đã áp dụng trong POM hoàn chỉnh ở mục 5.

- Java release và source encoding là **baseline luôn tồn tại trong model**, không phụ thuộc profile mặc định.
- Profile chỉ đổi `demo.mode`, là dữ liệu có ý nghĩa biến thiên.
- Khi cả `local` lẫn `ci` không active, `demo.mode=base` vẫn là giá trị hợp lệ.
- Khi thêm một profile mới, bạn không buộc phải sao chép mọi property chung vào đó.

Với cấu hình quan trọng như code signing, license scan hoặc policy của CI, không nên dựa **duy nhất** vào một profile active-by-default rồi giả định tác vụ luôn chạy. Đặt policy ở cấu hình chung hoặc có bước kiểm tra bắt buộc, tùy yêu cầu dự án.

## 10. Parent POM, child POM, settings.xml và dự án nhiều module

Quy tắc “cùng POM” càng quan trọng trong một build nhiều module:

~~~text
root/pom.xml                <-- POM cha / aggregator
├── <profiles>
│   └── parent-default (activeByDefault)
│
├── library/pom.xml         <-- Child POM
│   └── <profiles>
│       ├── local (activeByDefault)
│       └── ci
│
└── service/pom.xml         <-- Child POM khác
    └── <profiles>
        └── service-ci
~~~

**Inheritance (kế thừa)** và **aggregation (gom reactor)** không đồng nghĩa profile definitions được copy nguyên vẹn từ parent sang child:

- Profile definitions không được kế thừa nguyên khối. **Tác động của các profile đã active** trong parent có thể được kế thừa vào model con.
- `local` và `ci` khai báo trong `library/pom.xml` tương tác theo quy tắc **cùng POM của library**.
- `service-ci` của `service/pom.xml` không tự tắt `local` tại `library/pom.xml` chỉ vì cùng một reactor.
- `parent-default` của `root/pom.xml` cần được đánh giá trong ngữ cảnh parent, không coi activation ở mọi child là một công tắc chung duy nhất.
- Một profile trong `settings.xml` có phạm vi cấu hình riêng. Đừng mặc định rằng mọi profile settings đang active sẽ tự tắt active-by-default profile ở tất cả POM. Điều cần xác minh là **profile nào thực sự active trong POM chứa default**, cùng với cơ chế activation từ Maven/settings thực tế.

Từ root của reactor, có thể kiểm tra model theo module:

~~~bash
mvn -pl :library help:active-profiles
mvn -pl :library help:effective-pom
mvn -pl :service help:active-profiles
~~~

Đây là **lệnh minh họa** cho dự án thực sự có module `library`/`service` như sơ đồ; không phải các lệnh sẽ chạy được trong dự án mẫu một module ở mục 5.

**Profile cùng id ở nhiều POM** không mặc nhiên là cùng một definition. Khi dùng `-Pci` trong reactor, Maven có thể áp dụng activation theo những nơi có id tương ứng; cần xem log của từng module thay vì kết luận dựa trên một dòng hiển thị chung.

## 11. Tắt profile tường minh và lưu ý dấu nháy của shell

Maven cho phép vô hiệu hóa profile bằng tiền tố `!` hoặc `-` trước id. Dạng thuận tiện khi chạy đa shell là:

~~~bash
mvn -P=-local help:active-profiles
~~~

Với Bash/Zsh, dấu `!` có thể có ý nghĩa history expansion, nên nếu dùng dạng `!local` phải **quote hoặc escape**. Không sao chép bừa lệnh có `!` từ CMD sang Bash.

Cú pháp `-P=-local` hữu ích khi:

1. Muốn kiểm tra giá trị POM cơ sở khi không áp dụng default profile.
2. Cần tắt một profile có activation tự động nhưng vẫn giữ các profile khác.
3. Muốn thử một tổ hợp profile mà không sửa tệp `pom.xml`.

Nếu bạn muốn **bật lại profile mặc định cùng profile khác**, dùng `-Plocal,ci` như mục 4. Dấu `activeByDefault` chỉ quyết định trạng thái **mặc định**, không cấm explicit activation của chính profile đó.

Với Maven 4, việc chọn id profile **không tồn tại** có thể làm build bị từ chối. Tài liệu Maven 4 có cú pháp `?profile-id` để đánh dấu profile tùy chọn. Không sử dụng cú pháp này bừa bãi cho Maven 3 và không coi profile chưa tồn tại là cấu hình đúng.

## 12. Thực hành CI: chọn profile rõ ràng, không dựa vào mặc định

Ví dụ dự án mẫu có Maven Wrapper và JDK 17 trên GitHub Actions:

~~~yaml
name: Verify Maven profiles

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Display active profiles
        run: ./mvnw -Pci help:active-profiles
      - name: Build with explicit CI profile
        run: ./mvnw -B -ntp -Pci clean verify
~~~

Đây là workflow minh họa cho repository đã commit `mvnw`/`mvnw.cmd` và cấu hình Wrapper phù hợp. `setup-java` chọn JDK; Maven Wrapper pin bản Maven. `-Pci` xác định profile cần dùng. Vì `ci` active, `local` active-by-default trong cùng POM không được tính thêm.

Với property activation:

~~~yaml
- name: Build cloud mode
  run: ./mvnw -B -ntp -Dtarget.env=cloud clean verify
~~~

Lệnh trên kích hoạt `cloud` theo cấu hình POM mẫu; nó **không deploy ứng dụng lên cloud**. Việc deploy cần plugin/pipeline phù hợp và thông tin xác thực an toàn.

Để tránh khác biệt máy phát triển – CI:

- Ghi rõ profile được chạy trong tài liệu, script và CI.
- Pin plugin versions trong POM và Maven version qua Wrapper nếu dự án dùng.
- Tránh đặt giá trị bất biến quan trọng chỉ trong active-by-default profile.
- Không gắn bí mật vào `-Dpassword=...` vì dễ lọt vào history hoặc CI log.
- Dùng `help:active-profiles`/`help:effective-pom` khi behavior khác kỳ vọng.

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Không bật `-Pci` nhưng `local` chạy bình thường; bật `-Pci` thì Java release thiếu | Java release chỉ đặt trong `local` active-by-default, bị tắt khi `ci` active cùng POM. | Đặt release chung ngoài profiles hoặc bổ sung đúng cấu hình; so effective POM. |
| `local` mất hiệu lực khi truyền `-Dtarget.env=cloud` | Property kích hoạt profile `cloud` khác cùng POM, khiến `local` auto-off. | Dùng `help:active-profiles` và xem activation của `cloud`. |
| `-Plocal,ci` khiến cả hai cùng active | `local` đã được chọn tường minh; không còn chỉ phụ thuộc cờ default. | Xem hai profile trong `help:active-profiles`. |
| `-Pci,cloud` và `-Pcloud,ci` vẫn ra cùng một property | Thứ tự khai báo profile trong POM quan trọng hơn thứ tự CSV của `-P` khi merge tên trùng. | Mở `pom.xml` và `help:effective-pom`. |
| Có hai profile active-by-default cùng hoạt động | Không có profile khác được kích hoạt trong POM ấy, và cả hai đều đánh dấu default. | Xem danh sách active profiles, kiểm tra cấu hình trùng nhau. |
| Đổi `settings.xml` nhưng profile trong module khác không như dự đoán | Nguồn profile và phạm vi container khác nhau. | Xem `help:active-profiles` theo module và kích hoạt thật. |
| Chạy riêng module khác chạy từ root reactor | Parent, settings, profile activation hoặc dependency context khác. | Chạy cùng Maven version, options, JDK và so effective POM. |
| Đổi `-P` nhưng Java vẫn in mode của lần build cũ | Chưa chạy lại Maven Resources Plugin/`package`. | Chạy `clean package` rồi chạy Java, kiểm tra `target/classes/app.properties`. |
| Lệnh `-P!local` bị lỗi/biến mất ký tự trên Bash | `!` có thể kích hoạt lịch sử lệnh. | Dùng `-P=-local` hoặc quote/escape đúng shell. |
| `-Punknown` không hoạt động như mong muốn | Profile id không tồn tại hoặc Maven version khác quy tắc. | Kiểm tra danh sách profile/id; Maven 4 có yêu cầu chặt hơn. |
| `help:active-profiles` không tải được | Help Plugin chưa được cache hoặc repository lỗi. | Kiểm tra Maven/plugin/repository; không kết luận ngay về activation. |

Khi điều tra lỗi, đi theo thứ tự: **xác định POM/module chứa profile** → **liệt kê profiles active** → **xác định nguồn kích hoạt** → **đọc effective POM** → **chạy lại build sạch và xem kết quả**. Cách này phân biệt lỗi activation với lỗi merge cấu hình hoặc file `target/` đã cũ.

## 14. Checklist cấu hình activeByDefault an toàn

- [ ] Profile có `<id>` rõ ràng và mục đích sử dụng cụ thể.
- [ ] `activeByDefault` chỉ dành cho cấu hình dự phòng, không dành cho policy bắt buộc phải chạy mọi nơi.
- [ ] Các cấu hình bắt buộc như source encoding, Java release hoặc plugin version nền tảng được đặt **ngoài profile mặc định** nếu cần áp dụng cho mọi môi trường.
- [ ] Mọi profile có thể được kích hoạt trong **cùng POM** đã được xem xét về tác động làm default tắt.
- [ ] Nếu có nhiều profile ghi cùng property, thứ tự khai báo và kết quả merge đã được kiểm tra.
- [ ] CI gọi `-P` hoặc điều kiện activation rõ ràng, không phụ thuộc vào trạng thái mặc định mơ hồ.
- [ ] Dùng `help:active-profiles` và `help:effective-pom` để kiểm tra đúng module/POM.
- [ ] Kiểm tra lại output hoặc test sau khi thay profile; không dùng dữ liệu `target/` của lần trước để kết luận.
- [ ] Với parent/child đa module, phân biệt profile definition và tác động kế thừa.
- [ ] Nếu người dùng cần tắt profile mặc định, kiểm tra lệnh `-P=-profile-id` trong Maven version của dự án.

## 15. Câu hỏi tự kiểm tra

1. **`local` có `activeByDefault=true`. Chạy `mvn -Pci verify`, với `ci` cùng POM, `local` có tiếp tục active không?**  
   Không, nếu `local` chỉ được kích hoạt do cờ default. `ci` active tường minh sẽ làm `local` tự tắt.

2. **Có thể buộc `local` và `ci` cùng active không?**  
   Có: `mvn -Plocal,ci verify`. Cả hai được chọn tường minh. Khi chúng ghi cùng property, cần áp dụng quy tắc merge, không chỉ nhìn danh sách active.

3. **`cloud` được bật khi `-Dtarget.env=cloud`, `local` sẽ ra sao?**  
   Trong POM mẫu, `cloud` active theo property và `local` active-by-default bị tắt.

4. **Khi không có profile nào active, những giá trị trong `<properties>` ngoài `<profiles>` có biến mất không?**  
   Không. Đây là cấu hình cơ sở. Trong ví dụ mục 5, `demo.mode=base` vẫn có hiệu lực.

5. **`mvn -Pci,cloud` và `mvn -Pcloud,ci` có bắt buộc cho thứ tự ưu tiên ngược nhau không?**  
   Không. Với các profile trong cùng POM và property trùng tên, thứ tự khai báo trong POM mới là yếu tố quyết định theo quy tắc Maven.

6. **Chạy `mvn -Ddemo.mode=custom ...` có nhất thiết kích hoạt `ci` hoặc `cloud` không?**  
   Không. Nó là một user property, nhưng các profile ở POM mẫu chỉ có điều kiện riêng: `cloud` đòi `target.env=cloud`; `ci` đòi active tường minh. Một property khác không tự kích hoạt chúng.

7. **Vì sao phát sinh khác biệt khi bật một profile ở child, còn default profile nằm ở parent?**  
   Vì các profile được đánh giá trong container/POM tương ứng; profile definitions không được copy nguyên trạng như một danh sách chung. Cần kiểm tra trạng thái từng POM và tác động kế thừa.

8. **Đâu là cách xem trạng thái thật thay vì đoán từ tên profile?**  
   `mvn help:active-profiles` để biết profile nào active, `mvn help:effective-pom` để biết giá trị model cuối và lệnh build/test để xác nhận hành vi.

## 16. Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html) — mục *Active by default*, *Explicit profile activation*, *Profile Order* và *Profile Inheritance*.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html) — profile và `<activeProfiles>` trong `settings.xml`.
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html) — quan hệ POM, parent và aggregation.
- [Apache Maven Help Plugin — active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html) — liệt kê các profile đang hoạt động.
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html) — kiểm tra model đã áp dụng.
- [Apache Maven Help Plugin — evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html) — xem property sau khi profile được áp dụng.
- [Apache Maven Resources Plugin — filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html) — cơ chế nội suy resource trong ví dụ.

**Ghi nhớ:** `activeByDefault=true` nghĩa là **mặc định khi chưa có profile khác active trong cùng POM**, không phải “luôn bật”. Một profile được kích hoạt bằng `-P` hoặc điều kiện có thể làm default profile của POM ấy tự tắt. Khi nhiều profile cùng active, Maven hợp nhất cấu hình theo quy tắc model và thứ tự khai báo. Hãy đặt các cài đặt quan trọng dùng chung ngoài profiles, và xác minh bằng `help:active-profiles` cùng `help:effective-pom`.
