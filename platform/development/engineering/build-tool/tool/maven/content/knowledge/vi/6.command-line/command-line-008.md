# Làm mới kiểm tra phụ thuộc bằng Maven `-U` và giới hạn của tùy chọn này

## 1. Vấn đề `-U` giải quyết: Maven không hỏi repository ở mọi lần build

Khi một dự án Java khai báo dependency trong `pom.xml`, Maven phải tìm được artifact tương ứng để biên dịch, kiểm thử hoặc chạy plugin. Nó thường tra cứu **local repository** (mặc định `~/.m2/repository`) và, khi cần, **remote repositories** như Maven Central hoặc repository nội bộ của tổ chức.

Local repository chứa những artifact đã tải cùng metadata và thông tin về các lần truy xuất. Cơ chế cache giúp nhiều lần build không phải tải lại cùng một JAR hay gọi network liên tục. Đồng thời Maven có **chính sách thời điểm kiểm tra cập nhật** (`updatePolicy`) của repository. Vì vậy, một bản `SNAPSHOT` mới có thể đã được phát hành lên server nhưng lần build hiện tại vẫn dùng bản local trước đó cho tới lúc được phép kiểm tra lại.

Maven cũng có thể **ghi nhớ một lần phân giải thất bại**. Ví dụ ở lần trước nó tìm `com.example:shared-api:1.2.0` nhưng repository chưa có artifact này; lần chạy sau có thể báo việc tra cứu đã bị cache và chưa đến thời điểm thử lại. Sau khi phía phát hành upload artifact, bạn muốn Maven thử ngay mà không phải đợi hết chu kỳ kiểm tra.

`-U` là tùy chọn giúp xử lý đúng hai tình huống đó. Tuy nhiên, nó không phải nút “nâng cấp toàn bộ thư viện” và không thay thế việc sửa cấu hình khi dependency hoặc repository thực sự sai.

## 2. Chính xác `-U` có nghĩa là gì?

Cờ dòng lệnh `-U` là dạng viết ngắn của `--update-snapshots`. Trong Maven CLI, ý nghĩa thực tế được tài liệu chính thức mô tả là **buộc kiểm tra các bản release đang thiếu và các bản SNAPSHOT có cập nhật trên remote repositories**.

Hai phần cần nhớ:

1. **SNAPSHOT đã có tại local:** Maven được yêu cầu hỏi remote xem có bản SNAPSHOT mới hơn cho tọa độ đang được phân giải không. Nếu metadata/binary cần dùng đã thay đổi và repository truy cập được, Maven có thể tải nội dung mới.
2. **Release chưa được phân giải thành công:** Nếu một lần tìm artifact release từng thất bại và kết quả thất bại đang bị cache, `-U` cho phép thử kiểm tra lại ngay, ngay cả khi chưa hết khoảng chờ theo update policy. Nó **không** buộc tải lại một release đã có sẵn và được phân giải thành công ở local repository.

Nói cách khác, `-U` **ép kiểm tra khả năng cập nhật hoặc thử lại việc tìm artifact**, chứ không bảo đảm có một tệp mới được tải xuống. Nếu remote không có bản mới, cache đã đúng, server không truy cập được hoặc không cho phép tải SNAPSHOT, build có thể không khác gì lần trước.

**Điểm dễ hiểu sai:** tên `--update-snapshots` nhấn mạnh SNAPSHOT, nhưng hành vi vẫn bao gồm việc **thử lại đối với release đang thiếu**. Đây là hành vi đã được mô tả trong Maven CLI chính thức; không nên kết luận rằng `-U` “chỉ tác động SNAPSHOT”.

## 3. SNAPSHOT, release và cached failure khác nhau thế nào?

### 3.1. SNAPSHOT là tọa độ có thể trỏ đến bản build thay đổi

Giả sử một module khác đã xuất bản:

```text
com.example.team:shared-api:2.4-SNAPSHOT
```

Dự án consumer có đoạn POM sau (đây là **đoạn trích minh họa**, cần repository chứa artifact này để build được):

```xml
<dependency>
    <groupId>com.example.team</groupId>
    <artifactId>shared-api</artifactId>
    <version>2.4-SNAPSHOT</version>
</dependency>
```

Bên phát hành có thể tiếp tục triển khai những bản build mới dưới cùng **base version** `2.4-SNAPSHOT`. Remote repository thường có metadata để ánh xạ base version sang bản snapshot đã phát hành theo timestamp/build number. Maven có thể dựa vào metadata này để chọn bản hiện tại khi được phép kiểm tra.

Tình huống:

- Sáng: consumer tải bản `2.4-SNAPSHOT` đang có trên server.
- Trưa: nhóm phát hành upload một bản snapshot mới cùng base version.
- Chiều: consumer build lại. Nếu chưa đến thời điểm kiểm tra theo cache policy, Maven có thể dùng bản local từ sáng.
- Chạy `mvn -U test`: Maven buộc kiểm tra cập nhật ở remote; nếu tìm thấy snapshot phù hợp mới hơn, nó tải/cập nhật thông tin cần thiết rồi build với bản đã phân giải.

`-U` **không tạo bản snapshot mới**, không thực hiện `deploy` cho producer và không đổi dependency từ `2.4-SNAPSHOT` thành một version khác như `2.5-SNAPSHOT`.

### 3.2. Release thường được xem là artifact bất biến theo tọa độ

Ví dụ:

```text
org.apache.commons:commons-lang3:3.17.0
```

Nếu tệp release `3.17.0` đã có và được giải quyết thành công trong local repository, chạy `mvn -U verify` **không có nghĩa Maven phải tải lại JAR release này**. Phiên bản khai báo trong POM vẫn là `3.17.0`. Nếu bạn muốn dùng release `3.18.0`, cần cập nhật khai báo/`dependencyManagement` hoặc cấu hình phiên bản tương ứng sau khi xác nhận release đó tồn tại và phù hợp.

Tuy nhiên, giả sử lúc trước Maven đã tìm `3.17.0` nhưng repository trả về “not found” hoặc lần tra cứu lỗi và việc **phân giải release bị cache là thất bại**. Khi artifact có thể truy cập lại, `-U` cho phép Maven thử tìm ngay thay vì phải chờ hết chu kỳ kiểm tra. Nếu tọa độ sai hoặc server vẫn không có artifact, ép thử lại cũng tiếp tục thất bại.

### 3.3. Bảng quyết định nhanh

| Tình huống khi chạy build | `mvn -U ...` có tác dụng gì? | Điều không được kỳ vọng |
| --- | --- | --- |
| SNAPSHOT đã cache, remote có bản mới cùng base version | Buộc kiểm tra; có thể tải bản mới phù hợp | Không đổi `2.4-SNAPSHOT` thành `2.5-SNAPSHOT` |
| SNAPSHOT chưa có bản mới | Có thể kiểm tra và tiếp tục dùng bản đã có | Không tự tạo artifact mới |
| Release chưa tải được, lỗi “cached” | Buộc thử kiểm tra lại remote | Không biến tọa độ không tồn tại thành hợp lệ |
| Release đã tải và phân giải thành công | Thông thường tiếp tục dùng tệp release local | Không tải lại toàn bộ release chỉ vì có `-U` |
| Muốn đổi dependency từ bản release A sang B | Vẫn phải đổi version/config thích hợp | Không tự nâng phiên bản trong POM |
| Repository offline, sai URL hoặc không có quyền | Không giải quyết được lỗi mạng/quyền | Không “vượt” proxy, xác thực hay server |
| SNAPSHOT chỉ nằm ở máy producer, chưa được publish | Không thấy được qua remote repository | Không truy cập được local repository của máy khác |
| Dependency xung đột phiên bản trong dependency tree | Phân giải theo cùng quy tắc phiên bản | Không tự quyết định bản đúng cho ứng dụng |

## 4. Cách dùng `-U` trong dòng lệnh

`-U` là **tùy chọn cho lần chạy Maven hiện tại**, không phải lifecycle phase, plugin goal hay thay đổi lưu vào `pom.xml`.

Các lệnh thông dụng:

```bash
mvn -U test
mvn -U clean verify
mvn --update-snapshots package
mvn -U dependency:tree
```

- `mvn -U test`: thực hiện lifecycle đến `test`, đồng thời yêu cầu kiểm tra cập nhật theo cơ chế `-U` cho các artifact cần phân giải.
- `mvn -U clean verify`: dọn output build ở `target/`, sau đó chạy lifecycle đến `verify`; `-U` tác động cách Maven kiểm tra artifact từ repository.
- `mvn --update-snapshots package`: giống sử dụng `-U` nhưng viết tên dài.
- `mvn -U dependency:tree`: yêu cầu Maven phân giải dependencies cho goal hiển thị cây phụ thuộc; hữu ích để xem version nào đang được sử dụng. Goal của Maven Dependency Plugin có thể phải được tải vào lần chạy đầu.

Bạn cũng có thể đặt cờ sau các goal, ví dụ `mvn clean verify -U`, nhưng đặt trước goal giúp người đọc dễ nhận ra nó là tùy chọn CLI.

Nếu dự án đã có Maven Wrapper, lệnh tương đương trên Linux/macOS là:

```bash
./mvnw -U clean verify
```

Trên Windows:

```powershell
.\mvnw.cmd -U clean verify
```

Wrapper chỉ dùng được khi dự án đã cung cấp đầy đủ script và cấu hình wrapper. Nó giúp dùng Maven distribution mà dự án quy định, nhưng không tự đồng bộ Java runtime hay quyền truy cập repository.

**Không nhầm `-U` với `-o`:** `mvn -o test` là chế độ offline, không truy cập remote. Kết hợp `-o -U` không khiến Maven tải được nội dung mới từ server khi offline.

## 5. Ví dụ chạy được với Java 17: quan sát `-U` trong một project nhỏ

Ví dụ này cố ý dùng **release dependency** cho unit test, để chứng minh `-U` có thể chạy bình thường mà **không đổi version** hoặc bắt buộc tải lại thư viện đã có. Sau đó mục 6 sẽ giải thích riêng kịch bản SNAPSHOT nội bộ.

### 5.1. Tạo bộ khung

```text
maven-update-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/mavenupdate/App.java
    └── test/
        └── java/
            └── com/example/mavenupdate/AppTest.java
```

Bạn cần JDK 17 trở lên và Maven hỗ trợ JDK đang dùng. Lệnh `mvn -version` sẽ cho biết JDK thật sự mà Maven sử dụng. Nếu plugin/dependency chưa có ở local repository, Maven cần kết nối repository để tải trong lần đầu.

### 5.2. Tệp `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-update-demo</artifactId>
    <version>1.0.0</version>
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
                <version>3.13.0</version>
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

Trong POM này, `junit-jupiter:5.11.4` là release dependency dùng cho test; Compiler Plugin và Surefire Plugin cũng khai báo version cụ thể. Cờ `-U` **không sửa bất kỳ version nào trong POM**. `maven.compiler.release=17` chỉ yêu cầu đầu ra tương thích Java 17; bạn vẫn cần JDK có khả năng biên dịch với `--release 17`.

### 5.3. Tệp `src/main/java/com/example/mavenupdate/App.java`

```java
package com.example.mavenupdate;

public final class App {
    private App() {
    }

    public static String message() {
        return "Maven -U demo";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

### 5.4. Tệp `src/test/java/com/example/mavenupdate/AppTest.java`

```java
package com.example.mavenupdate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("Maven -U demo", App.message());
    }
}
```

Test dùng JUnit 5, tên lớp `AppTest` để Surefire nhận diện. Nó xác nhận giá trị trả về của chương trình, không phụ thuộc vào output log Maven.

### 5.5. Chạy và đọc kết quả đúng cách

Trong thư mục `maven-update-demo` (nơi có `pom.xml`):

```bash
mvn -version
mvn clean verify
mvn -U clean verify
java -cp target/classes com.example.mavenupdate.App
```

Lệnh Java cuối in **chính xác**:

```text
Maven -U demo
```

Hai lần gọi Maven đều build cùng một project; không có SNAPSHOT dependency nào trong POM, nên `-U` **không tạo sự khác biệt bắt buộc về version hoặc output**. Lần đầu có thể tải plugin/JUnit, lần sau tận dụng cache. Thông báo tải file, thời gian và log Surefire không phải stdout cố định; xem test report trong `target/surefire-reports` nếu cần.

Đây là điểm học tập quan trọng: **chạy thành công với `-U` không chứng minh đã cập nhật bất kỳ dependency nào**. Để kiểm chứng hiệu quả `-U`, phải biết có SNAPSHOT mới trên remote hoặc có một lần phân giải release bị cache thất bại và giờ artifact đã truy cập được.

## 6. Thí nghiệm tư duy: khi cùng `SNAPSHOT` có nhiều bản được deploy

Giả sử một nhóm phát hành thư viện nội bộ `com.example.team:shared-api:2.4-SNAPSHOT` vào **snapshot repository** mà consumer đã cấu hình và được cấp quyền. Cần phân biệt hành động của producer và consumer:

| Thời điểm | Producer / remote repository | Consumer |
| --- | --- | --- |
| T1 | Xuất bản bản SNAPSHOT thứ nhất | `mvn test` tải bản hiện có |
| T2 | Xuất bản bản SNAPSHOT thứ hai cùng `2.4-SNAPSHOT` | Chưa build lại |
| T3 | Remote chứa bản mới | `mvn test` có thể vẫn dùng bản đã cache do update policy |
| T4 | Không có thêm lần deploy | `mvn -U test` buộc kiểm tra; có thể tải bản SNAPSHOT mới và dùng cho lần build đó |

Trước khi thử, kiểm tra rằng **producer đã deploy** artifact mới lên **đúng repository** mà consumer nhìn thấy. Nếu producer chỉ chạy `mvn package` trên máy riêng, consumer không thể nhìn thấy một tệp nằm ở `target/` của máy đó. `mvn install` cũng chỉ cài vào **local repository của máy đang chạy**, không phát hành lên remote.

Nếu consumer và producer thuộc cùng một multi-module Maven reactor, khi build đúng reactor, Maven có thể sử dụng output module tương ứng trực tiếp. `-U` chủ yếu hữu ích khi dự án phải **phân giải artifact từ repository**; nó không thay thế việc thêm module vào reactor hoặc build/publish module đúng nơi.

## 7. `updatePolicy` và vì sao Maven không luôn kiểm tra mọi lúc

Tần suất truy cập remote được điều khiển bởi chính sách repository. Trong cấu hình POM hoặc `settings.xml`, policy của `releases` và `snapshots` có thể được khai báo riêng. Đoạn XML sau chỉ minh họa **phần chính sách bên trong một repository**:

```xml
<snapshots>
    <enabled>true</enabled>
    <updatePolicy>daily</updatePolicy>
</snapshots>
```

Nó không phải POM độc lập; cần đặt trong `<repository>` hoặc cấu hình repository phù hợp. Tương tự, phần `<releases>` có chính sách riêng.

Các giá trị `updatePolicy` phổ biến:

| Giá trị | Ý nghĩa |
| --- | --- |
| `always` | Thường xuyên kiểm tra cập nhật mỗi lần phân giải thích hợp |
| `daily` | Kiểm tra theo ngày; thường là mặc định |
| `interval:60` | Khoảng kiểm tra 60 phút |
| `never` | Không chủ động kiểm tra lại artifact đã có theo chu kỳ thông thường |

Cờ `-U` yêu cầu Maven **ép kiểm tra trong lần chạy đó** đối với các trường hợp mà cờ này áp dụng, thay vì chỉ chờ chính sách thời gian thông thường. Nhưng `-U` **không tự bật SNAPSHOT trong repository bị cấu hình `<snapshots><enabled>false</enabled></snapshots>`**, không biến Central thành kho phát hành snapshot nội bộ, và không thay thế URL, mirror, quyền hay xác thực.

**Local và remote repository là hai khái niệm khác nhau:**

- `~/.m2/repository`: thư mục cache/cài đặt artifact trên máy (đường dẫn thực tế có thể được chỉnh trong Maven settings).
- Repository từ xa: nguồn mà Maven kết nối để tìm artifact/metadata qua URL được cấu hình.
- `.lastUpdated` và metadata cục bộ có thể lưu trạng thái lần kiểm tra hoặc lỗi truy xuất, nhưng không nên dựa vào việc xóa ngẫu nhiên các tệp này như giải pháp đầu tiên.

Không cần thay `updatePolicy` toàn cục thành `always` chỉ vì một lần gặp bản snapshot cũ: việc đó có thể gây nhiều lần truy cập mạng không cần thiết. Một lệnh `mvn -U ...` có phạm vi hẹp hơn và dễ kiểm soát.

## 8. Những giới hạn bắt buộc phải hiểu về `-U`

### 8.1. Không nâng version trong POM

Dependency khai báo `1.4.0` vẫn là `1.4.0`. Cờ `-U` không dò bản mới nhất rồi viết lại thành `1.5.0`, không sửa BOM/`dependencyManagement`, và không thay version plugin được ghim. Để nâng cấp dependency, phải chọn version, kiểm tra tương thích, chỉnh POM/quản lý version và chạy test. Có thể dùng Maven Versions Plugin để **xem/gợi ý** các version khi cần, nhưng đó là thao tác khác `-U`.

### 8.2. Không tải lại tất cả release JAR đã cache

Một release đã có tại local repository và được phân giải thành công thông thường sẽ tiếp tục được sử dụng. Nếu nghi ngờ một artifact release bị hỏng hoặc local cache bị sai, `-U` **không phải** công cụ bảo đảm tải lại chính file đó. Cần chẩn đoán nguyên nhân, có thể dùng cơ chế xóa cache **có chọn lọc** bằng Maven Dependency Plugin hoặc tác vụ quản trị cache phù hợp; đừng xóa toàn bộ `.m2` theo phản xạ.

### 8.3. Không khắc phục tọa độ hoặc repository sai

Nếu POM ghi sai `groupId`, `artifactId`, version, classifier hoặc type, thì tra cứu lại bao nhiêu lần cũng có thể cho cùng lỗi. Nếu SNAPSHOT chỉ có ở repo nội bộ nhưng consumer chỉ trỏ đến Maven Central hoặc snapshots bị disable, `-U` không sửa cấu hình đó.

### 8.4. Không vượt qua lỗi mạng, proxy, TLS, auth hoặc rate limit

`401 Unauthorized`, `403 Forbidden`, lỗi chứng chỉ, proxy, DNS, timeout hay `429 Too Many Requests` là vấn đề kết nối/quyền/hạn mức. `-U` có thể tạo thêm yêu cầu kiểm tra nhưng không giải quyết các nguyên nhân ấy; lặp lại quá thường xuyên còn có thể làm tình trạng throttling nặng hơn.

### 8.5. Không bảo đảm đã có SNAPSHOT mới

Maven chỉ có thể tải thứ repository thực sự phục vụ. Ngay cả khi producer nói “đã build xong”, cần phân biệt giữa `package`, `install` và `deploy`, cũng như việc metadata repo/proxy có đồng bộ chưa. Ngoài ra, không phải mọi version `-SNAPSHOT` đều được phép truy cập từ bất kỳ repository nào.

### 8.6. Không thay thế dependency mediation

Khi hai thư viện kéo các phiên bản khác nhau của một transitive dependency, Maven vẫn áp dụng cơ chế giải quyết version. `-U` không tự chọn “phiên bản tốt nhất” cho code và không làm biến mất các lỗi API binary như `NoSuchMethodError`. Dùng `mvn dependency:tree` và khai báo/`dependencyManagement` thích hợp để xử lý mâu thuẫn.

### 8.7. Không sửa mã, chạy thêm bài test hay dọn local repository

`-U` không sửa source, không bổ sung test, không xóa `target/` và không dọn `~/.m2/repository`. `clean` là lifecycle riêng để dọn đầu ra build; `test`/`verify` quyết định các bước build và kiểm thử. Vì thế `mvn -U clean verify` kết hợp **ba ý nghĩa khác nhau** trong một lệnh.

### 8.8. Cờ có hiệu lực trong lần gọi Maven đó

`mvn -U verify` không tự thay đổi POM để mọi lần `mvn verify` về sau luôn ép kiểm tra. Nếu cần policy lâu dài, hãy xem xét cấu hình repository, quy trình CI và cách quản lý SNAPSHOT, thay vì nhầm cờ lệnh một lần với cấu hình vĩnh viễn.

## 9. Cách chẩn đoán khi dependency “không chịu cập nhật”

Bắt đầu từ đúng thông báo lỗi và loại phiên bản, thay vì chỉ thử lặp lại `-U`.

| Dấu hiệu | Hành động đúng trọng tâm |
| --- | --- |
| Dùng `x.y-SNAPSHOT` nhưng nghi ngờ bản local cũ | Xác nhận bản mới đã deploy lên đúng snapshot repo; thử `mvn -U test` và xem log resolution |
| Lỗi nói việc phân giải đã “cached” và sẽ chưa retry | Xác nhận artifact giờ đã tồn tại/URL đúng; thử `mvn -U test` một lần |
| Release `x.y.z` đã tải nhưng muốn release mới | Chọn version mới rồi sửa POM/BOM; `-U` không tự nâng version |
| Maven không tìm thấy snapshot mặc dù đã deploy | Kiểm tra repo/mirror/profile, `snapshots enabled`, quyền và metadata |
| Một thành phần chạy trên máy producer nhưng máy consumer không tìm thấy | Xác nhận producer đã `deploy` tới kho chia sẻ hoặc reactor/local repo sử dụng đúng |
| `401`/`403`/`429`, proxy, TLS hoặc timeout | Khắc phục xác thực/hạ tầng/throttling; không ép check liên tục |
| `NoSuchMethodError` hoặc hành vi không tương thích | Kiểm tra dependency tree, classpath và version mediation |
| Đang chạy `-o` | Tắt offline và bảo đảm remote truy cập được trước khi thử cập nhật |

Các lệnh hữu ích, chạy ở thư mục có `pom.xml`:

```bash
mvn -version
mvn dependency:tree
mvn help:effective-pom
mvn -U -e test
```

- `mvn -version`: xác nhận phiên bản Maven và JDK.
- `mvn dependency:tree`: xem dependency nào đang tham gia, cả transitive.
- `mvn help:effective-pom`: xem version/config hiệu lực sau kế thừa và quản lý dependency.
- `mvn -U -e test`: retry/check update theo `-U` và in stack trace lỗi nếu cần.

Khi cần chẩn đoán sâu có thể dùng `mvn -U -X test` để xem debug; log có thể dài và phản ánh cấu hình repository, vì vậy cần xử lý thông tin nhạy cảm trước khi chia sẻ. Nếu nghi mirror/repository được cấu hình sai, xem `settings.xml` hiệu lực và POM, nhất là `mirrors`, `profiles`, `repositories`, `pluginRepositories` và quyền sử dụng kho.

**Lưu ý về Maven version:** chi tiết CLI có thể thay đổi giữa các nhánh Maven. Với một công cụ cụ thể, kiểm tra `mvn -h`. Các phiên bản Maven mới có thể bổ sung tùy chọn riêng để kiểm tra artifact/metadata; kiến thức cốt lõi của `-U` trong bài vẫn là **kiểm tra missing releases và updated snapshots**, không phải nâng cấp tự động mọi dependency.

## 10. Thực hành kiểm chứng đúng tác dụng của `-U`

**Bài tập 1 — trường hợp chỉ có release.** Chạy ví dụ Java 17 ở mục 5 hai lần, lần sau thêm `-U`. Kiểm tra JUnit vẫn là `5.11.4` trong POM và unit test vẫn PASS. Kết quả này **không** đủ để kết luận Maven đã tải phiên bản dependency mới.

**Bài tập 2 — trường hợp SNAPSHOT nội bộ (khi có quyền dùng repository).** Nhờ module producer phát hành hai bản SNAPSHOT liên tiếp vào cùng remote repo theo quy trình nhóm. Consumer chạy `mvn test` rồi `mvn -U test`. So sánh metadata, log resolution và tính năng đã thay đổi. Đừng giả định có bản mới chỉ từ thông báo `BUILD SUCCESS`.

**Bài tập 3 — giải thích lỗi.** Với mỗi trường hợp dưới đây, quyết định `-U` có thể giúp không:

1. Release `1.0.0` đã cache, muốn dùng `1.1.0`: **không**, cần đổi version.
2. Release `1.0.0` từng bị báo thiếu, giờ đã xuất bản: **có thể giúp**, vì buộc thử lại.
3. SNAPSHOT cùng base version mới deploy trên repo đang bật snapshots: **có thể giúp**, vì buộc kiểm tra cập nhật.
4. Đang offline: **không tải được bản mới**, dù kèm `-U`.
5. Sai `groupId` hoặc bị `403`: **không sửa được**, cần xử lý tọa độ/quyền.

Cách nhớ: **`-U` là yêu cầu kiểm tra lại remote trong một lần build, dành cho SNAPSHOT cập nhật và release chưa tìm được; nó không đồng nghĩa “update tất cả thư viện”.**

### Tài liệu tham khảo chính thức

- [Apache Maven — CLI Options Reference (Maven 3)](https://maven.apache.org/ref/3-LATEST/maven-embedder/cli.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories)
- [Apache Maven — Settings Reference: repositories và updatePolicy](https://maven.apache.org/settings.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
