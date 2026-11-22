# Gọi Maven plugin bằng tiền tố hoặc tọa độ đầy đủ có phiên bản

## 1. Đọc đúng một lệnh Maven

Trong một dự án Java, Maven dùng **plugin** để thực hiện công việc cụ thể như biên dịch, kiểm thử, đóng gói, kiểm tra dependency hoặc sinh báo cáo. Mỗi plugin có thể cung cấp một hay nhiều **goal** (đơn vị thao tác mà plugin thực thi).

Ba lệnh sau có hình thức gần nhau nhưng mang ý nghĩa khác nhau:

```bash
mvn package
mvn dependency:tree
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

- `mvn package` yêu cầu Maven chạy đến **phase `package` của vòng đời build**. Plugin goal nào được thực thi tùy packaging, các ràng buộc phase và cấu hình POM.
- `mvn dependency:tree` gọi **goal `tree` của một plugin** theo tiền tố ngắn `dependency`. Maven phải xác định tiền tố này trỏ đến plugin nào và dùng phiên bản nào.
- `mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree` gọi trực tiếp **goal `tree` của Maven Dependency Plugin phiên bản `3.6.1`**, với định danh plugin đầy đủ.

Hai lệnh cuối có thể cùng in cây dependency của dự án, nhưng chỉ khi lệnh ngắn thực sự phân giải đến **cùng plugin và cùng phiên bản** thì ta mới có cơ sở so sánh hành vi dưới cùng cấu hình. Tên goal `tree` không tự chỉ định phiên bản plugin.

Điểm mấu chốt: **phase thuộc vòng đời; goal thuộc plugin; prefix là tên rút gọn để tìm plugin; tọa độ đầy đủ chỉ rõ plugin và phiên bản**.

## 2. Cú pháp gọi plugin từ dòng lệnh

### 2.1. Dạng ngắn: `prefix:goal`

```text
mvn <prefix>:<goal>
```

Ví dụ:

```bash
mvn dependency:tree
mvn help:effective-pom
mvn compiler:compile
```

Ở đây:

- `dependency` ánh xạ đến plugin có `artifactId` là `maven-dependency-plugin`.
- `help` ánh xạ đến `maven-help-plugin`.
- `compiler` ánh xạ đến `maven-compiler-plugin`.
- `tree`, `effective-pom`, `compile` là **tên goal** của các plugin tương ứng, không phải phase bắt buộc của Maven.

Tên rút gọn có lợi cho thao tác hằng ngày và dễ ghi nhớ. Đổi lại, Maven phải thực hiện hai công việc: tìm plugin từ prefix và xác định phiên bản plugin sẽ chạy. Kết quả có thể phụ thuộc POM hiệu lực, cấu hình máy người dùng, metadata repository và trạng thái kho cục bộ.

### 2.2. Dạng đầy đủ có phiên bản: `groupId:artifactId:version:goal`

```text
mvn <groupId>:<artifactId>:<version>:<goal>
```

Ví dụ dùng một phiên bản Maven Dependency Plugin có tài liệu phát hành cụ thể:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Bóc tách từng thành phần:

| Thành phần | Giá trị trong ví dụ | Vai trò |
| --- | --- | --- |
| `groupId` | `org.apache.maven.plugins` | Nhóm phát hành plugin |
| `artifactId` | `maven-dependency-plugin` | Tên artifact chứa plugin |
| `version` | `3.6.1` | Phiên bản plugin yêu cầu chạy |
| `goal` | `tree` | Thao tác phân tích cây dependency |

Dấu hai chấm phân tách **tọa độ plugin và goal**. Đây không phải đường dẫn tệp, cũng không phải một dependency được thêm vào ứng dụng. Maven tải/giải quyết plugin và các thành phần cần thiết để thực thi goal theo POM và cấu hình repository.

Maven cũng hỗ trợ cú pháp `groupId:artifactId:goal` không khai báo trực tiếp phiên bản trong lệnh. Tuy nhiên, nếu mục tiêu là xác định rõ một bản plugin, nên dùng đủ **bốn thành phần**, hoặc quản lý phiên bản plugin nhất quán trong POM.

**Phiên bản `3.6.1` ở đây chỉ phục vụ ví dụ tái lập và có trang tài liệu riêng**. Khi áp dụng thật, chọn bản plugin còn được dự án hỗ trợ, kiểm tra yêu cầu Maven/JDK và chính sách cập nhật của nhóm.

### 2.3. Không nhầm prefix với artifactId hoặc phase

`maven-dependency-plugin` là `artifactId`, trong khi `dependency` là prefix. Lệnh `mvn maven-dependency-plugin:tree` không phải cách viết thay thế đáng tin cậy cho `mvn dependency:tree`: bộ phân giải prefix tìm theo **ánh xạ prefix**, không đơn thuần nhận mọi artifactId.

`mvn compile` là yêu cầu chạy phase `compile`. `mvn compiler:compile` là gọi goal biên dịch của plugin; hai lệnh có thể liên quan trong dự án Java thông thường nhưng không tương đương trong mọi POM. Phase có thể bao gồm các goal khác và xử lý bước chuẩn bị trước nó.

## 3. Maven tìm plugin như thế nào khi dùng prefix?

Một prefix là **ánh xạ từ tên ngắn sang `groupId:artifactId`**. Khi gọi `mvn dependency:tree`, Maven cần tìm plugin gắn với `dependency` trước khi có thể chạy goal `tree`.

### 3.1. Quy ước tên giúp nhận diện, nhưng metadata mới là cơ chế phân giải

Các plugin chính thức của Maven thường có tên theo mẫu `maven-<prefix>-plugin`. Plugin bên thứ ba thường dùng mẫu `<prefix>-maven-plugin`. Ví dụ `maven-dependency-plugin` thường dùng prefix `dependency`.

Plugin có thể khai báo một prefix tùy chỉnh. Khi plugin được xuất bản, thông tin ánh xạ prefix được cung cấp qua **metadata của nhóm plugin trong repository**, được Maven truy vấn và lưu ở kho cục bộ. Vì vậy, không nên tự suy đoán rằng mọi plugin đều có prefix đúng bằng phần tên ta thấy sau khi bỏ các từ “maven” hoặc “plugin”.

Trong quá trình phân giải, Maven xem cấu hình dự án và tra cứu thông tin về plugin trong các nhóm được chỉ định, dùng metadata và những repository được phép. Nếu không tìm được ánh xạ, Maven có thể báo lỗi:

```text
No plugin found for prefix '...' in the current project and in the plugin groups ...
```

Dòng trên là **mẫu lỗi minh họa**, không phải toàn bộ log cố định. Nguyên nhân có thể là prefix sai, thiếu plugin group, metadata chưa lấy được, repository/proxy bị chặn hoặc cấu hình máy khác nhau.

### 3.2. Những nhóm plugin được tìm mặc định

Trong Maven, hai nhóm thường được tìm cho lệnh dạng prefix là:

- `org.apache.maven.plugins`: các plugin chính thức, chẳng hạn Compiler, Surefire, Dependency và Help.
- `org.codehaus.mojo`: nhóm plugin cộng đồng được Maven hỗ trợ tìm theo prefix.

Nếu sử dụng plugin từ nhóm thứ ba khác và muốn gọi bằng prefix, người dùng có thể bổ sung nhóm đó trong `settings.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
    <pluginGroups>
        <pluginGroup>com.example.build.plugins</pluginGroup>
    </pluginGroups>
</settings>
```

Đây là **mẫu cấu hình**; `com.example.build.plugins` là tên nhóm giả định, không đại diện cho plugin có thể chạy ngay. `settings.xml` cá nhân thường nằm tại thư mục `.m2` của người dùng. Không đặt `pluginGroups` bên trong `pom.xml`.

Thứ tự nhóm có thể ảnh hưởng kết quả nếu nhiều plugin cùng khai báo một prefix. Do vậy, rút gọn lệnh bằng cách thêm quá nhiều plugin group cũng có thể tạo ra xung đột hoặc làm khó kiểm tra plugin nào thực sự được gọi. Với plugin ít dùng hoặc từ bên thứ ba, việc ghi tọa độ đầy đủ thường dễ kiểm toán hơn.

**Không đồng nhất `pluginGroups` với `pluginRepositories`:** `pluginGroups` cho Maven biết **tìm tiền tố trong những nhóm nào**; `pluginRepositories` và cấu hình repository/mirror cho Maven biết **lấy artifact plugin và metadata từ đâu**. Thêm plugin group không tự cấp quyền truy cập repository, và khai báo repository không tự đưa mọi group vào danh sách tìm prefix.

## 4. Ví dụ thực hành: cùng một goal với hai cách gọi

Tạo một thư mục trống, đặt `pom.xml` sau vào gốc. Đây là POM Maven có thể sử dụng để chạy Dependency Plugin; không cần mã Java để minh họa việc đọc dependency, vì mục tiêu bài này là **cú pháp lệnh Maven**.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>plugin-cli-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.10.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-dependency-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Ý nghĩa:

- Project có một dependency ví dụ với `scope=test`. Goal `tree` sẽ thể hiện dependency được giải quyết, bao gồm các quan hệ bắc cầu thực tế.
- `maven-dependency-plugin` được khai báo trong `build/plugins` với phiên bản `3.6.1`. Đó là một cách giữ phiên bản plugin ổn định khi dự án gọi goal trực tiếp bằng prefix.
- Không có `<executions>` gắn plugin này vào phase; việc khai báo plugin ở đây **không làm goal `tree` tự chạy trong mọi lần `mvn package`**.

Từ đúng thư mục chứa POM, chạy:

```bash
mvn dependency:tree
```

Rồi chạy cùng goal bằng tọa độ đã chốt:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Trong ví dụ này, hai lệnh đều hướng tới **Maven Dependency Plugin `3.6.1` và goal `tree`**. Cây hiển thị có thể có nhiều dòng vì các dependency bắc cầu; không nên ghi một stdout cố định khi chưa khóa trạng thái repository và toàn bộ dependency của dự án.

Sau đó thử tham số riêng của goal:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -DoutputType=dot -DoutputFile=dependencies.dot
```

Ở phiên bản plugin này, `outputType=dot` yêu cầu biểu diễn cây dependency ở định dạng DOT, còn `outputFile=dependencies.dot` yêu cầu ghi nội dung đó ra tệp trong thư mục dự án. Đây là tham số của **goal `tree`**, không phải tùy chọn áp dụng cho mọi plugin Maven. Giá trị của từng tham số phải tra ở tài liệu goal/version đang dùng.

Nếu đã cài Maven Wrapper cho chính dự án, thay `mvn` bằng `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên Windows PowerShell. Wrapper quản lý **phiên bản Maven chạy lệnh**; nó không tự chốt phiên bản của mọi plugin được gọi.

## 5. Cố định phiên bản trong POM và tác động của lệnh đầy đủ

### 5.1. Vì sao lệnh ngắn cần một chiến lược phiên bản?

Lệnh `mvn dependency:tree` không chứa phiên bản plugin. Maven sẽ giải quyết phiên bản từ cấu hình POM có hiệu lực (khi được khai báo phù hợp) hoặc qua cơ chế phân giải plugin. Nếu dự án không quản lý phiên bản rõ ràng, lần chạy ở các môi trường khác nhau có thể chọn phiên bản khác, gặp khác biệt về goal, tham số, kết quả hoặc yêu cầu chạy.

Để tăng khả năng tái lập, Maven khuyến nghị khai báo **phiên bản plugin** trong POM, thường quản lý tập trung qua `build/pluginManagement` ở parent POM. Ví dụ dưới đây là **một phần POM**, đặt trong `<build>`:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-dependency-plugin</artifactId>
            <version>3.6.1</version>
        </plugin>
    </plugins>
</pluginManagement>
```

`pluginManagement` quản lý phiên bản/cấu hình cho plugin mà các module sử dụng, nhưng **không tự buộc một goal phải chạy trong một phase**. Nếu plugin cần tham gia vòng đời, phải hiểu plugin đó được áp dụng thế nào, nó có goal được ràng buộc sẵn cho packaging không và có cần `executions` hay không. Đừng xem việc “đã khai báo pluginManagement” là bằng chứng goal đã chạy.

Với bài thực hành ở phần 4, ta khai báo plugin trực tiếp trong `<build><plugins>` để thấy ngay plugin được dùng và phiên bản của nó. Trong dự án nhiều module, có thể chuyển quản lý phiên bản sang parent để tránh khai báo không nhất quán giữa các module.

### 5.2. Khi lệnh đã ghi phiên bản, Maven chạy phiên bản nào?

Nếu người dùng gõ:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

thì phiên bản plugin yêu cầu thực thi là **`3.6.1`**. Không nên giả định Maven sẽ thay lệnh đó bằng một phiên bản khác trong `pluginManagement`. Cấu hình plugin trong POM vẫn có thể ảnh hưởng hành vi goal phù hợp, nhưng **tọa độ phiên bản trên lệnh** là yêu cầu cụ thể về artifact plugin.

Có thể dùng một phiên bản mới hơn trên dòng lệnh để thử, nhưng cần kiểm tra tương thích trước khi thay vào quy trình chính thức. Nếu CI phải tái lập được build, hãy ghi nhận cả phiên bản Maven/Wrapper, phiên bản plugin, POM có hiệu lực và repository được dùng.

Một điểm khác: **chốt phiên bản plugin chưa đồng nghĩa toàn bộ build đã tuyệt đối tái lập**. Kết quả còn phụ thuộc dependency, phiên bản JDK, thông số cấu hình, plugin dependency, repository mirror, artifact snapshot và môi trường chạy.

## 6. Phân biệt gọi goal trực tiếp và chạy phase của vòng đời

Xem các lệnh:

```bash
mvn test
mvn surefire:test
mvn package
mvn dependency:tree
```

`mvn test` chạy các phase liên quan tới `test` theo vòng đời của dự án; ví dụ thường bao gồm bước xử lý resources, biên dịch mã chính, biên dịch test và chạy test với dự án Java. `mvn surefire:test` gọi riêng goal của Surefire Plugin. Lệnh goal trực tiếp có thể bỏ qua các bước chuẩn bị mà vòng đời đã chạy trước đó, do đó nếu lớp test chưa được biên dịch thì hành vi có thể khác.

`mvn package` đóng gói dự án theo packaging và các goal được gắn vào các phase đến `package`. `mvn dependency:tree` chỉ yêu cầu phân tích dependency; nó **không mặc nhiên tương đương đóng gói, biên dịch hay chạy test**.

Một số plugin goal được thiết kế để chạy trực tiếp, một số có tiền điều kiện từ build và một số có thể kích hoạt/fork vòng đời theo metadata của goal. Vì thế không có quy tắc đúng cho mọi plugin rằng “gọi goal chỉ thực thi đúng một bước và không thể phát sinh phase khác”. Hãy đọc phần **Attributes/Requires Project/Requires Dependency Resolution/Executes Phase** của tài liệu goal cụ thể.

Nếu muốn chạy nhiều mục tiêu trong một lệnh, Maven nhận các mục tiêu được liệt kê theo thứ tự:

```bash
mvn clean package
mvn package org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

Lệnh thứ hai yêu cầu đóng gói trước rồi chạy goal `tree`. Tuy nhiên, không nên dùng cách ghép tùy ý để khắc phục mọi lỗi: cấu trúc phase, ràng buộc goal và điều kiện đầu vào vẫn phải được hiểu và kiểm tra.

## 7. Truyền tham số cho plugin từ CLI

Maven cho phép truyền **user properties** qua `-Dkey=value`. Plugin goal có thể công bố những tham số sử dụng các property đó. Ví dụ với Dependency Plugin `3.6.1`:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -Dscope=compile
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -DoutputType=dot
```

Ở đây `scope` dùng lọc phạm vi dependency, còn `outputType` thay đổi định dạng trình bày. Lệnh trên không tự thay đổi dependency khai báo trong POM.

**Không suy diễn tên property từ tên tham số một cách máy móc**: nhiều plugin dùng tên khác nhau, đôi khi có tiền tố riêng. Trước khi dùng một cờ `-D`, xem đúng tài liệu goal/version hoặc chạy goal trợ giúp mà plugin hỗ trợ:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-dependency-plugin -Dgoal=tree -Ddetail
```

Đây là lệnh gọi **Maven Help Plugin** để xem mô tả plugin/goal; nó cũng phải được Maven phân giải và tải về nếu chưa có. Với dự án yêu cầu cố định tuyệt đối mọi công cụ chạy trên CI, có thể chốt riêng phiên bản Help Plugin khi sử dụng chẩn đoán.

Các tùy chọn như `-B` (batch mode) hoặc `-o` (offline mode) là tùy chọn CLI chung của Maven; chúng khác với `-DoutputType=dot` vốn được một plugin goal cụ thể hiểu.

## 8. Sử dụng trong dự án nhiều module và CI

Ở dự án Maven reactor nhiều module, chạy goal ở parent có thể thực hiện goal cho nhiều module tùy đặc tính goal và cấu trúc reactor. Khi chỉ muốn thao tác trên một module:

```bash
mvn -pl :service-api org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree
```

`:service-api` ở đây là **artifactId giả định**, cần thay bằng artifactId thật của module. `-pl` chọn module; khi cần xây dựng thêm module phụ thuộc trong cùng reactor, `-am` có thể thêm các module bắt buộc tương ứng, nhưng việc chọn goal nào chạy ở module nào còn tùy tính chất plugin và mô hình project.

Trong CI, lệnh có phiên bản rõ ràng dễ được người review đọc và đối chiếu. Tuy nhiên, không nhất thiết viết GAV đầy đủ cho *mọi* goal nếu parent POM đã quản lý phiên bản plugin đúng cách và pipeline có kiểm soát. Một chiến lược thực tế là:

- **Thao tác phát triển thường ngày:** dùng lệnh ngắn như `mvn dependency:tree` khi POM đã quản lý phiên bản.
- **Script CI, chạy plugin hiếm hoặc debug sai khác phiên bản:** ưu tiên khai báo phiên bản trong POM hoặc sử dụng tọa độ `groupId:artifactId:version:goal` rõ ràng.
- **Plugin bên thứ ba:** xem xét plugin group, nguồn plugin, chính sách repository và thông tin phát hành; không chạy mã plugin không rõ nguồn chỉ vì có thể gõ được tọa độ.

Plugin là **mã thực thi chạy trong quá trình build**, vì vậy cần xem thay đổi plugin hay repository trong pull request như thay đổi có tác động tới môi trường CI. Việc ghim phiên bản giúp kiểm soát thay đổi, nhưng còn cần kiểm soát nguồn artifact và quyền truy cập token/secrets.

## 9. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `No plugin found for prefix ...` | Sai prefix, thiếu plugin group, metadata không truy cập được | Kiểm tra prefix chính thức, `settings.xml`, repository/proxy; thử tọa độ đầy đủ của plugin đã xác minh |
| `Plugin ... could not be resolved` | Plugin hoặc phiên bản không có trong nguồn được phép, lỗi mạng/mirror hoặc cache | Xem GAV/version, `pluginRepositories`, mirror, lỗi gốc trong log; không đổi ngẫu nhiên sang phiên bản không được duyệt |
| Goal không tồn tại | Tên goal sai hoặc goal chưa có trong phiên bản đang chạy | Mở tài liệu đúng phiên bản, xem danh sách goal và thử Help Plugin |
| Cùng `prefix:goal` nhưng máy A/B có hành vi khác | Version, effective POM, profile, settings hoặc repository metadata khác | So sánh phiên bản Maven, cấu hình plugin, `mvn help:effective-pom` và log phân giải plugin |
| Lệnh đầy đủ chạy, lệnh ngắn lỗi | Prefix mapping hoặc plugin group không xác định dù artifact có thể tải bằng GAV | Kiểm tra prefix metadata, nhóm plugin và settings; cân nhắc dùng GAV trong CI |
| Goal trực tiếp thất bại vì thiếu đầu ra | Goal cần classes/resources/test output đã tạo trước | Chạy phase phù hợp như `mvn test`/`mvn package` trước, hoặc dùng đúng vòng đời thay vì gọi goal lẻ |
| Plugin tải được nhưng tham số `-D` không có tác dụng | Đã dùng sai tên user property hoặc sai version goal | Xem “User Property” trong tài liệu đúng version; kiểm tra effective POM và cấu hình goal |
| `-o` thất bại dù dependency ứng dụng đã có cache | Plugin, plugin dependency hoặc metadata cần thiết chưa sẵn trong local repository | Chuẩn bị cache đúng trên môi trường kết nối mạng, không coi dependency ứng dụng là toàn bộ đầu vào build |

Khi cần log chi tiết, Maven có tùy chọn `-X` để xem thông tin chẩn đoán. Lưu ý log debug có thể chứa URL nội bộ hoặc thông tin môi trường; xử lý log theo quy định bảo mật dự án.

## 10. Checklist đọc và viết một lệnh plugin

Khi gặp một lệnh Maven trong README hoặc pipeline, hãy xác định lần lượt:

1. **Phần trước dấu hai chấm là gì?** `dependency` là prefix, còn `org.apache.maven.plugins:maven-dependency-plugin:3.6.1` xác định rõ plugin bằng GAV.
2. **Goal nào được yêu cầu?** `tree` là thao tác phân tích dependency; không thể suy luận nó sẽ compile, test hay package nếu không xem mô tả goal.
3. **Phiên bản plugin đến từ đâu?** Được ghi trong lệnh, trong POM/parent POM hay phải phân giải từ repository?
4. **Plugin được tìm ở đâu?** Các nhóm tìm prefix, `pluginRepositories`, settings, mirror và trạng thái local repository có phù hợp không?
5. **Goal cần POM hoặc đầu ra trước đó không?** Xem tài liệu goal cụ thể; `dependency:tree` cần dự án Maven, nhưng các goal khác có thể có điều kiện khác.
6. **Tham số CLI thuộc Maven hay thuộc goal?** Kiểm tra chính xác `-D` property theo tài liệu phiên bản plugin.
7. **Lệnh có tái lập được trên máy khác/CI không?** Chốt phiên bản plugin và Maven khi cần, kiểm soát repository, và xác minh chạy trên môi trường sạch.

Cách viết lệnh phù hợp với nhu cầu:

```bash
# Gọn cho thao tác hằng ngày trong dự án đã quản lý plugin version
mvn dependency:tree

# Chỉ rõ plugin, phiên bản và goal để dễ đối chiếu
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree

# Chỉ rõ phiên bản và tham số goal cho một đầu ra cụ thể
mvn org.apache.maven.plugins:maven-dependency-plugin:3.6.1:tree -DoutputType=dot -DoutputFile=dependencies.dot
```

Các lệnh được chạy tại thư mục có `pom.xml`, với Maven và truy cập repository được cấu hình phù hợp. Phiên bản trong ví dụ được chọn để minh họa cú pháp đã được tài liệu chính thức xác nhận; khi nâng phiên bản plugin cần kiểm tra lại khả năng tương thích và tham số goal.

### Tài liệu chính thức để tra cứu

- [Apache Maven — Introduction to Plugin Prefix Resolution](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Guide to Developing Java Plugins, cú pháp gọi goal](https://maven.apache.org/guides/plugin/guide-java-plugin-development)
- [Apache Maven Dependency Plugin 3.6.1 — tree goal](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.6.1/tree-mojo.html)
- [Apache Maven — Guide to Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
