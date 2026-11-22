# Quản lý tệp nguồn và bỏ qua đầu ra build trong Git với Maven

## 1. Tư duy nền tảng: cái gì là nguồn, cái gì là sản phẩm?

Maven tổ chức dự án Java sao cho **mã nguồn và cấu hình** là đầu vào, còn các tệp trong quá trình biên dịch, kiểm thử và đóng gói là **đầu ra có thể tạo lại**. Git lưu lịch sử các đầu vào cần thiết để cả nhóm xây dựng cùng một phiên bản ứng dụng. Nếu commit toàn bộ đầu ra của Maven, mỗi lần chạy build có thể tạo ra hàng trăm tệp nhị phân thay đổi mà người khác khó đọc, dễ gây xung đột và làm kho mã nguồn phình to.

Quy tắc thực hành là:

- **Theo dõi (track) bằng Git** những tệp do nhóm viết, xem xét và bảo trì: `pom.xml`, mã trong `src/`, tài liệu, quy tắc kiểm thử, cấu hình build dùng chung, cấu hình CI và Maven Wrapper nếu dự án dùng.
- **Bỏ qua (ignore)** đầu ra Maven có thể sinh lại, trước hết là các thư mục `target/`.
- **Không đưa bí mật vào Git**: thông tin xác thực, token hoặc tệp cấu hình cá nhân cần được quản lý riêng; `.gitignore` chỉ giúp tránh đưa nhầm tệp chưa theo dõi, không phải cơ chế bảo mật cho dữ liệu đã commit.

Hai khái niệm cần phân biệt:

- **Mã nguồn**: thứ quyết định cách chương trình hoạt động; thay đổi nó phải được review. Ví dụ `src/main/java`, `src/test/java`, `src/main/resources`, `src/test/resources`.
- **Đầu ra build**: thứ Maven tạo từ mã nguồn và cấu hình. Ví dụ `target/classes`, `target/test-classes`, báo cáo Surefire, JAR/WAR dưới `target/`.

Ví dụ một cấu trúc dự án:

```text
hello-maven/
├── .gitignore                       [nên commit]
├── pom.xml                          [nên commit]
├── README.md                        [nên commit]
├── src/
│   ├── main/
│   │   ├── java/dev/example/App.java     [nên commit]
│   │   └── resources/app.properties      [nên commit nếu dùng]
│   └── test/
│       ├── java/dev/example/AppTest.java [nên commit]
│       └── resources/example.json        [nên commit nếu dùng]
└── target/                          [Maven sinh ra; bỏ qua]
    ├── classes/
    ├── test-classes/
    ├── surefire-reports/
    └── hello-maven-1.0.0-SNAPSHOT.jar
```

Các chú thích trong sơ đồ chỉ hướng dẫn phân loại, không phải một phần của tên tệp.

**Nguyên lý kiểm chứng:** khi người khác clone repository, họ nên có thể chạy một lệnh như `mvn clean verify` để tạo lại đầu ra cần thiết. Build có thể còn phụ thuộc phiên bản JDK, plugin, thư viện và cấu hình môi trường; vì thế những lựa chọn cần tái lập cũng phải được ghi rõ trong POM và tài liệu dự án.

## 2. Những thư mục Maven cần biết trước khi viết `.gitignore`

Với cấu trúc Maven chuẩn, các nguồn chính thường nằm ở:

| Đường dẫn | Vai trò | Xử lý với Git |
| --- | --- | --- |
| `pom.xml` | Tọa độ dự án, dependencies, plugins, cấu hình build | Commit |
| `src/main/java/` | Mã Java được biên dịch cho ứng dụng/thư viện | Commit |
| `src/main/resources/` | Cấu hình và tài nguyên thực sự dùng bởi chương trình | Commit nếu thuộc mã nguồn; không đưa secret |
| `src/test/java/` | Kiểm thử tự động; không nằm trong JAR chính theo mặc định | Commit |
| `src/test/resources/` | Fixture, dữ liệu mẫu và tài nguyên kiểm thử | Commit nếu cần để test |
| `.mvn/`, `mvnw`, `mvnw.cmd` | Maven Wrapper và cấu hình Maven chia sẻ trong dự án, khi có | Thường commit các phần dùng chung |
| `.github/workflows/` hoặc cấu hình CI tương đương | Quy trình build, test, kiểm tra chất lượng | Commit |
| `target/classes/` | Bytecode `.class` và resources sau compile | Ignore |
| `target/test-classes/` | Bytecode và tài nguyên kiểm thử đã xử lý | Ignore |
| `target/surefire-reports/` | Báo cáo unit test | Ignore trên máy làm việc; CI lưu làm artifact nếu cần |
| `target/failsafe-reports/` | Báo cáo kiểm thử tích hợp khi dùng Failsafe | Ignore trong Git |
| `target/generated-sources/` | Mã được plugin sinh trong quá trình build | Ignore khi có thể sinh lại một cách tin cậy |
| `target/*.jar`, `target/*.war` | Sản phẩm đóng gói | Ignore; xuất bản bằng kho artifact riêng khi cần |

Một số thư mục trong bảng sẽ **chỉ xuất hiện khi Maven hoặc plugin tương ứng chạy**. Không bắt buộc phải tạo sẵn `target/` hay `resources/`. Sau `mvn clean`, Maven thường xóa `target/`, và các lệnh build tiếp theo sẽ tạo lại.

Vì `target/` là thư mục đầu ra mặc định của Maven, bỏ qua toàn bộ thư mục này đơn giản và đúng hơn so với việc liệt kê từng đuôi `.class`, `.jar`, `.xml` sinh ra bên trong. Việc này vẫn giữ được các tệp JAR hoặc XML **có chủ đích** trong nguồn, ví dụ JAR dùng làm fixture kiểm thử hay tệp XML trong `src/main/resources`.

## 3. `.gitignore` hoạt động như thế nào?

`.gitignore` là tệp văn bản chứa các **mẫu đường dẫn** để Git không đề xuất đưa các tệp *chưa được theo dõi* phù hợp mẫu vào repository. Tạo tệp `.gitignore` ở gốc repository:

```gitignore
# Maven: bo qua dau ra build cua moi module
target/

# Tep tam theo du an, khi thuc su duoc sinh ra
*.log

# Tep phat sinh theo he dieu hanh
.DS_Store
Thumbs.db
```

Trong bài này, dòng quan trọng nhất là `target/`. Dấu `/` cuối cho biết mẫu dành cho **thư mục**. Khi đặt trong `.gitignore` ở gốc repository, mẫu `target/` không có dấu `/` đầu nên áp dụng cho thư mục có tên `target` ở các cấp bên dưới, gồm cả `module-a/target/` và `module-b/target/` trong dự án nhiều module.

So sánh:

```gitignore
target/        # bat thu muc target/ o moi cap trong pham vi .gitignore
/target/       # chi bat thu muc target/ ngay canh .gitignore nay
```

Nếu một tệp dữ liệu nguồn **cố ý** có tên trùng mẫu, phải điều chỉnh lại quy tắc: `*.log` sẽ bỏ qua cả các mẫu log cần commit trong `src/test/resources/`. Vì vậy, mẫu `*.log` trong ví dụ chỉ nên giữ nếu cả nhóm thống nhất log là đầu ra tạm; với dự án có fixture `.log`, có thể thay bằng một đường dẫn cụ thể như `runtime-logs/`.

Các quy tắc khác cần nhớ:

- Dòng bắt đầu bằng `#` là chú thích. Dòng trống không ảnh hưởng.
- `*.iml` khớp các tệp kết thúc bằng `.iml`; `build-temp/` khớp thư mục tên `build-temp`.
- Dấu `!` phủ định mẫu ignore ở phạm vi phù hợp: `!.env.example` cho phép giữ tệp mẫu khi đã bỏ qua `.env.*`. Tuy nhiên, Git **không tự lấy lại tệp** bên trong một thư mục cha vẫn đang bị bỏ qua; muốn dùng ngoại lệ sâu phải cho phép Git đi qua các thư mục cha.
- Một repository có thể có nhiều tệp `.gitignore`. Tệp đặt trong thư mục con áp dụng cho đường dẫn dưới thư mục đó và có thể bổ sung/ghi đè các mẫu theo quy tắc ưu tiên của Git.
- `.gitignore` là một tệp cần commit để cả nhóm dùng cùng chính sách. Quy tắc riêng của máy có thể đặt trong `.git/info/exclude` hoặc `core.excludesFile` toàn cục.

**Lưu ý quan trọng:** `.gitignore` không tự xóa tệp trên ổ đĩa và không tự bỏ theo dõi tệp đã được commit. Đây là nguyên nhân rất phổ biến khiến `target/` vẫn xuất hiện trong `git status` dù đã thêm dòng `target/`.

## 4. Mẫu `.gitignore` thực tế cho dự án Maven

Có thể bắt đầu bằng mẫu gọn sau rồi chỉnh theo chính sách đội nhóm:

```gitignore
# Dau ra build cua Maven, gom ca multi-module
target/

# Secret va cau hinh ca nhan trong thu muc du an
.env
.env.*
!.env.example
settings.local.xml

# File tam he dieu hanh/trinh soan thao
.DS_Store
Thumbs.db
*.swp

# File cua IDE khi nhom khong chia se cau hinh IDE
.idea/
*.iml
.classpath
.project
.settings/
```

Giải thích các lựa chọn:

- `target/` là quy tắc Maven quan trọng nhất, có thể giữ nguyên ở phần lớn dự án.
- `.env`, `.env.*` và `settings.local.xml` chỉ là những tên tệp **ví dụ** cho cấu hình cá nhân. Tên thật cần khớp cách dự án quản lý môi trường. `!.env.example` cho phép commit một tệp mẫu **không chứa secret**, nếu có.
- Những mẫu IDE như `.idea/`, `.classpath`, `.project` và `.settings/` phụ thuộc thỏa thuận dự án. Có nhóm muốn commit một vài thiết lập editor dùng chung; không nên mặc định loại bỏ mọi tệp cấu hình IDE của nhóm.
- `*.swp` là tệp tạm của một số editor; quy tắc này có thể bỏ nếu dự án không sử dụng.
- **Không thêm `*.java`, `*.xml`, `*.jar` hoặc `.mvn/` vào mẫu bỏ qua một cách vô điều kiện.** Java/XML thuộc mã nguồn và POM; JAR có thể là fixture hoặc bộ phận của Maven Wrapper; `.mvn/` thường chứa cấu hình quan trọng để build đồng nhất.

Nếu dự án của bạn tạo thêm `dependency-reduced-pom.xml` bằng Maven Shade Plugin, hoặc một thư mục log chuyên dụng, hãy kiểm tra nó thực sự là sản phẩm sinh ra trước khi bổ sung mẫu tương ứng. Không nên đoán rằng một tệp tên lạ luôn là đầu ra build.

## 5. Ví dụ dự án Java 17: Git chỉ giữ đầu vào, Maven tạo đầu ra

Tạo thư mục `hello-maven` và cấu trúc:

```text
hello-maven/
├── .gitignore
├── pom.xml
└── src/
    ├── main/java/dev/example/App.java
    └── test/java/dev/example/AppTest.java
```

Tạo `pom.xml` như sau:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>hello-maven</artifactId>
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

Mã chính `src/main/java/dev/example/App.java`:

```java
package dev.example;

public final class App {
    private App() {}

    public static int sum(int a, int b) {
        return Math.addExact(a, b);
    }

    public static void main(String[] args) {
        System.out.println(sum(2, 3));
    }
}
```

Kiểm thử `src/test/java/dev/example/AppTest.java`:

```java
package dev.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AppTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, App.sum(2, 3));
    }

    @Test
    void rejectsIntegerOverflow() {
        assertThrows(ArithmeticException.class,
                () -> App.sum(Integer.MAX_VALUE, 1));
    }
}
```

Trong `.gitignore` đặt tối thiểu:

```gitignore
target/
```

Tại gốc dự án, với JDK 17+ và Maven khả dụng:

```bash
mvn clean verify
java -cp target/classes dev.example.App
```

Lệnh `java` in đúng:

```text
5
```

`mvn clean verify` chạy biên dịch mã chính, biên dịch test, chạy hai phép kiểm thử rồi đóng gói JAR. Nếu thành công, bạn thường thấy:

```text
target/classes/dev/example/App.class
target/test-classes/dev/example/AppTest.class
target/surefire-reports/
target/hello-maven-1.0.0-SNAPSHOT.jar
```

Tất cả đường dẫn vừa liệt kê đều bắt đầu bằng `target/` và **không cần commit**. Ngược lại, `pom.xml`, `App.java` và `AppTest.java` là nguồn đã tạo ra chúng và cần nằm trong Git.

Để thấy chính sách Git áp dụng, nếu đây là dự án mới và chưa được quản lý bằng Git, khởi tạo repository bằng:

```bash
git init
git status --short --untracked-files=all
git check-ignore -v target/classes/dev/example/App.class
```

`git status --short` hiển thị các tệp chưa theo dõi như `pom.xml`, `.gitignore` và tệp nguồn, nhưng không liệt kê nội dung `target/` vì đã bị bỏ qua. `git check-ignore -v` chỉ ra mẫu và tệp `.gitignore` giải thích vì sao `App.class` bị ignore; kết quả có hình thức tương tự:

```text
.gitignore:1:target/    target/classes/dev/example/App.class
```

Số dòng có thể thay đổi nếu `.gitignore` có thêm các dòng trước `target/`. Khi muốn liệt kê cả đường dẫn bị ignore, dùng:

```bash
git status --ignored --short
```

Khi đó có thể thấy dòng `!! target/`. Hai ký tự `!!` ở chế độ ngắn chỉ đường dẫn đang bị ignore, **không biểu thị lỗi Maven**.

Chỉ đưa các tệp cần quản lý vào index:

```bash
git add .gitignore pom.xml src
git status --short
```

Các tệp được đưa vào vùng stage ở trạng thái `A` nếu mới. Bạn có thể review `git diff --cached` trước khi commit theo quy trình của nhóm. `target/` tiếp tục nằm ngoài index.

## 6. Khi `target/` đã từng được Git theo dõi

Trường hợp thường gặp: trước đây ai đó đã chạy `git add .` khi chưa có `.gitignore`, khiến `target/classes`, báo cáo test hoặc JAR xuất hiện trong các commit. Thêm `target/` vào `.gitignore` **không đủ**, vì Git vẫn theo dõi những tệp đã ghi vào index.

Bước 1: xem những tệp trong thư mục đầu ra ở root hiện đang được theo dõi:

```bash
git ls-files -- target/
```

Nếu danh sách có tệp và bạn đã xác nhận đây là đầu ra sinh lại, sử dụng:

```bash
git rm -r --cached -- target/
```

`--cached` xóa các đường dẫn phù hợp **khỏi Git index**, nhưng để nguyên tệp trên ổ đĩa làm việc. Tùy cấu trúc dự án, bước này tạo các mục `D` (xóa khỏi index) trong `git status --short`; đó là thay đổi đang chờ commit, không phải lỗi mất tệp vật lý. Không dùng `git rm -r target/` nếu muốn giữ các tệp cục bộ, vì thiếu `--cached` có thể xóa cả chúng khỏi thư mục làm việc.

Bước 2: xem lại thay đổi trước khi đưa vào lịch sử:

```bash
git status --short
git diff --cached --stat
```

Bước 3: khi đã thấy chỉ các tệp build bị bỏ theo dõi, tạo commit thay đổi chính sách theo quy trình làm việc của nhóm. Sau đó các lần build mới sẽ không tự đưa `target/` vào danh sách tệp chưa theo dõi.

Với dự án nhiều module, `git rm -r --cached -- target/` **chỉ xử lý đường dẫn `target/` ở gốc được chỉ định**. Kiểm tra các module có đầu ra đã tracked, ví dụ:

```bash
git ls-files -- module-a/target/ module-b/target/
```

Nếu kết quả có các tệp thực sự là đầu ra, có thể bỏ theo dõi từng thư mục tương ứng:

```bash
git rm -r --cached -- module-a/target/ module-b/target/
```

Các lệnh với đường dẫn trong ví dụ giả định những module này tồn tại và thực sự có tệp đang được theo dõi; không chạy máy móc cho module không có. Việc bỏ theo dõi không tự xóa các blob nhị phân đã tồn tại trong **lịch sử commit cũ**. Nếu lịch sử chứa secret, ngoài việc ngừng theo dõi còn cần thu hồi/thay credential và quy trình xử lý lịch sử thích hợp.

## 7. Dự án Maven nhiều module có cần nhiều `.gitignore`?

Giả sử một repository có POM cha và hai module:

```text
shopping-service/
├── .gitignore
├── pom.xml
├── domain/
│   ├── pom.xml
│   ├── src/main/java/
│   └── target/
└── api/
    ├── pom.xml
    ├── src/main/java/
    ├── src/test/java/
    └── target/
```

Chỉ cần tệp `.gitignore` ở gốc chứa `target/` là đủ để bỏ qua `domain/target/` và `api/target/` khi chúng không bị theo dõi từ trước. Không cần sao chép quy tắc `target/` vào mọi module. Nếu thêm `.gitignore` ở một module vì có thư mục tạm riêng, tệp đó bổ sung quy tắc cho phạm vi của module.

Để kiểm tra chính xác một đường dẫn:

```bash
git check-ignore -v domain/target/classes/dev/example/Domain.class
git check-ignore -v api/target/surefire-reports/example.txt
```

Có thể kiểm tra đường dẫn dù module chưa sinh đủ mọi tệp; công cụ dùng đường dẫn để tra mẫu ignore. Khi một tệp đã được Git theo dõi, lệnh mặc định có thể không báo vì `.gitignore` không loại tệp tracked; khi cần kiểm tra **mẫu bỏ qua độc lập với index**, dùng `git check-ignore --no-index -v <path>`.

**Ngoại lệ cần cân nhắc:** nếu một module cố ý sử dụng thư mục tên `target` để chứa dữ liệu nguồn (không phải đầu ra), quy tắc `target/` sẽ quá rộng. Khi đó nên đổi vị trí dữ liệu nguồn hoặc viết mẫu giới hạn phạm vi cho phù hợp, thay vì buộc Git bỏ qua một phần nguồn quan trọng.

## 8. Maven Wrapper là đầu vào build, đừng bỏ nhầm

**Maven Wrapper** cho phép người khác chạy Maven qua các script của dự án thay vì tự chọn một phiên bản Maven đã cài. Một dự án có Wrapper thường có:

```text
mvnw
mvnw.cmd
.mvn/
└── wrapper/
    └── maven-wrapper.properties
```

Tùy phiên bản và cách tạo Wrapper, trong `.mvn/wrapper/` còn có thể có `maven-wrapper.jar` hoặc các tệp hỗ trợ khác. Nếu dự án sử dụng những tệp này để khởi động Wrapper, chúng là **đầu vào cần được kiểm soát phiên bản**, không phải đầu ra thông thường nằm dưới `target/`.

Khi nhóm đã cấu hình Wrapper, ví dụ chạy:

```bash
./mvnw clean verify
```

Trên Windows dùng:

```powershell
.\mvnw.cmd clean verify
```

Nếu dùng script `mvnw` trên Unix/Linux, tệp cần có quyền thực thi trong Git theo quy trình của nhóm. Wrapper giúp đồng nhất **phiên bản Maven**, nhưng bản thân nó không tự cài một phiên bản JDK phù hợp. Vẫn cần đảm bảo môi trường Java tương thích.

Các tệp `.mvn/maven.config`, `.mvn/jvm.config` hoặc `.mvn/extensions.xml`, nếu có và chứa tùy chọn dùng chung hợp lệ, cũng thường cần commit để cả nhóm build cùng cách. Không đặt token hoặc mật khẩu trong đó. **Tránh mẫu bỏ qua toàn bộ `.mvn/`**, vì dễ khiến một bản clone thiếu cấu hình/Wrapper.

## 9. Phân biệt tệp cấu hình dự án với bí mật cá nhân

Không phải mọi tệp cấu hình đều thuộc cùng một nhóm:

- **Cấu hình có thể chia sẻ:** `pom.xml`, `application-example.properties`, `.env.example` (chỉ chứa placeholder không nhạy cảm), quy tắc định dạng, cấu hình CI và dữ liệu fixture không nhạy cảm. Những tệp này nên có lịch sử Git.
- **Cấu hình riêng của máy:** endpoint cục bộ, đường dẫn trên máy lập trình viên, token cá nhân, mật khẩu và chứng chỉ bí mật. Nên đọc qua biến môi trường, kho bí mật CI hoặc cơ chế cấu hình an toàn riêng.
- **Tệp do quá trình build sinh ra:** lớp `.class`, báo cáo kiểm thử, JAR/WAR trong `target/`; không nên commit dù chúng không chứa bí mật.

Maven thường đọc credential của người dùng từ `~/.m2/settings.xml` (ngoài thư mục dự án), trong khi `pom.xml` chỉ chứa ID server hoặc cấu hình không nhạy cảm. Không copy nội dung `settings.xml` có mật khẩu vào repo.

Một mẫu phân biệt bản mẫu và bản thật:

```gitignore
.env
.env.*
!.env.example
```

Đặt `.env.example` với các tên biến và giá trị giả (ví dụ `DB_HOST=localhost`, `DB_PASSWORD=replace-me`), còn `.env` thực tế chỉ nằm tại máy người dùng. Git không tự tạo tệp `.env` từ tệp mẫu; ứng dụng hoặc hướng dẫn thiết lập cần nói rõ cách cấu hình.

**`.gitignore` không phải biện pháp bảo mật tuyệt đối:** người dùng vẫn có thể `git add -f` để ép thêm tệp bị ignore; file đã commit vẫn nằm trong lịch sử; người khác có thể sao chép dữ liệu ra kênh khác. Kiểm tra nội dung trước khi stage và dùng công cụ quét secret khi phù hợp. Nếu một secret đã được commit, việc thêm dòng ignore không làm nó biến mất khỏi lịch sử, và phải xử lý credential bị lộ.

## 10. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Commit cả `target/` | Nhiều tệp nhị phân thay đổi, PR ồn và xung đột | Thêm `target/` vào `.gitignore`; bỏ tracked output khỏi index nếu đã commit |
| Thêm `target/` rồi tưởng mọi file cũ biến mất khỏi Git | File đã tracked vẫn hiện trong diff | Dùng `git ls-files -- target/` và `git rm -r --cached -- target/` sau khi xác minh |
| Bỏ qua toàn bộ `*.jar` | Có thể bỏ nhầm Maven Wrapper JAR hoặc fixture thực sự cần | Ignore `target/` theo đường dẫn đầu ra |
| Bỏ qua `pom.xml`, `src/test/` hoặc tài nguyên test | Clone không thể build/test giống bản gốc | Commit mã chính, test và cấu hình build dùng chung |
| Bỏ qua `.mvn/` mà dự án dùng Wrapper | Script Wrapper thiếu tệp hỗ trợ hoặc cấu hình | Commit `mvnw`, `mvnw.cmd` và các tệp Wrapper cần thiết |
| Dùng `/target/` ở gốc trong dự án nhiều module | Chỉ root `target/` bị ignore, module target vẫn hiện | Dùng `target/` cho mọi module |
| Dùng `*.log` khi fixture test là `.log` | Mất dấu dữ liệu kiểm thử cần tái hiện lỗi | Thu hẹp mẫu vào thư mục log thực sự sinh ra |
| Dùng `git rm -r target/` để sửa ignore | Có thể xóa tệp vật lý trên máy | Dùng `--cached` sau khi kiểm tra file đã tracked |
| Tin rằng `.gitignore` xóa secret khỏi lịch sử | Credential vẫn tồn tại trong commit cũ | Thu hồi secret và xử lý lịch sử theo quy trình an toàn |
| Chỉ dựa vào JAR đã có trong workspace | Không biết JAR có còn đúng với mã nguồn hiện tại | Chạy `mvn clean verify` và coi CI/build log là bằng chứng build |

## 11. Quy trình làm việc hằng ngày

Một vòng làm việc ổn định cho nhóm dùng Git và Maven:

1. **Clone/pull** mã nguồn gồm POM, source, test, cấu hình dùng chung.
2. **Build bằng Maven**: `mvn clean verify` hoặc Wrapper tương ứng; Maven tạo `target/` tại từng module khi cần.
3. **Sửa mã nguồn và test** trong `src/`. Build lại; chỉ tệp nguồn và cấu hình thật sự đã sửa cần được Git nhận diện.
4. **Kiểm tra Git trước khi stage**: `git status --short`. Nếu một file từ `target/` xuất hiện là tracked, tìm nguyên nhân và sửa index/chính sách ignore.
5. **Chọn file cần stage**: dùng `git add` cho những tệp nguồn/cấu hình xác định, hoặc review kỹ trước khi dùng `git add -A`.
6. **Xem diff** (`git diff`, `git diff --cached`) và commit theo quy trình của nhóm. CI nên có build và kiểm thử tự động dựa trên nội dung đã commit.
7. **Phân phối artifact qua nơi phù hợp** như kho Maven repository hoặc artifact của CI. Không biến Git thành nơi lưu mọi JAR build từ mỗi máy.

Các lệnh kiểm tra nhanh nên ghi nhớ:

```bash
# Kiem tra phan thay doi Git nhin thay
git status --short

# Hoi mau ignore nao dang ap dung cho duong dan
git check-ignore -v target/classes/dev/example/App.class

# Xem co file nao trong target/ o root da tracked khong
git ls-files -- target/

# Kiem tra bat ky file bi ignore (bao gom target/)
git status --ignored --short

# Build lai tu trang thai sach va chay test
mvn clean verify
```

Lưu ý: `mvn clean` có chủ đích xóa đầu ra ở `target/`. Chỉ chạy nó khi bạn không cần giữ những tệp build cục bộ chưa sao lưu; không chỉnh sửa thủ công dữ liệu quan trọng trong `target/`.

## 12. Tự thực hành và kiểm tra hiểu biết

Thực hiện trên dự án `hello-maven` ở mục 5:

1. Chạy `mvn clean verify`; xác định vị trí `App.class`, `AppTest.class`, báo cáo test và JAR. Chỉ ra vì sao chúng là đầu ra có thể sinh lại.
2. Chạy `git status --short` trước và sau khi thêm `target/` vào `.gitignore` (chỉ trong repository thử nghiệm chưa tracked build output). Đối chiếu thay đổi hiển thị.
3. Dùng `git check-ignore -v target/classes/dev/example/App.class`; giải thích mẫu nào đang làm Git bỏ qua tệp.
4. Giả lập hai module `domain/` và `api/` có `target/`; xác định vì sao một dòng `target/` ở gốc đủ áp dụng cho cả hai.
5. Giả sử một đồng nghiệp đã commit `target/` từ trước. Giải thích vì sao thêm `.gitignore` chưa đủ và tác dụng chính xác của `git rm -r --cached -- target/`.
6. Xếp `pom.xml`, `src/test/resources/input.json`, `target/surefire-reports`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`, `target/hello-maven-1.0.0-SNAPSHOT.jar` thành hai nhóm: **cần commit** và **nên ignore** (giả định dự án dùng Maven Wrapper).
7. Nếu muốn người khác tạo lại cùng artifact, chỉ commit mã Java đã đủ chưa? Chưa: cần cả POM, test, tài nguyên, cấu hình build quan trọng và thông tin môi trường/JDK.

Hoàn thành bài khi bạn có thể trả lời: **“Nếu tôi xóa `target/`, clone lại repository rồi chạy Maven thì tôi có tái tạo được các đầu ra cần thiết không?”** Với dự án được cấu hình đúng và các dependency/môi trường khả dụng, câu trả lời phải là có. Đây là mục đích thực tế của việc quản lý nguồn chuẩn và giữ đầu ra build ra khỏi Git.

## 13. Tài liệu tham khảo

- [Maven — Introduction to the Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html)
- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Wrapper Plugin](https://maven.apache.org/wrapper/)
- [Git — gitignore](https://git-scm.com/docs/gitignore)
- [Git — git rm](https://git-scm.com/docs/git-rm)
- [Git — git check-ignore](https://git-scm.com/docs/git-check-ignore)
