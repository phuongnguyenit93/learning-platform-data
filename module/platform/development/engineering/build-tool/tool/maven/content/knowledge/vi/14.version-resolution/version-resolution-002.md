# Quy tắc đường dẫn gần nhất và thứ tự khai báo khi cùng độ sâu trong Maven

## 1. Khi nào Maven phải chọn giữa nhiều phiên bản?

Maven tự thu thập các **dependency bắc cầu (transitive dependencies)** của thư viện được khai báo trong `pom.xml`. Vì nhiều thư viện có thể cùng phụ thuộc một artifact nhưng ở **các phiên bản khác nhau**, Maven cần xác định phiên bản nào thực sự tham gia **dependency graph/classpath** của project đang build.

Hãy tưởng tượng ứng dụng `app` dùng hai thư viện `lib-a` và `lib-b`:

```text
app
├── lib-a:1.0
│   └── shared-utils:1.0
└── lib-b:1.0
    └── shared-utils:2.0
```

Đây là **sơ đồ khái niệm**, không phải các artifact được khẳng định tồn tại trên Maven Central. Nếu cả hai đường đều được phép truyền dependency xuống app, Maven cần phân giải xung đột giữa `shared-utils:1.0` và `shared-utils:2.0`.

Hai quy tắc căn bản được Maven mô tả là:

1. **Nearest definition wins (đường dẫn gần nhất thắng):** Maven chọn phiên bản ở **đường phụ thuộc ngắn nhất** từ project gốc đang được build tới artifact đó.
2. **First declaration wins (khai báo trước thắng khi bằng độ sâu):** nếu những đường ứng viên có cùng số cạnh/độ sâu, thứ tự khai báo dependency quyết định ứng viên được chọn trước.

**Điều cần nhớ:** Maven không tự chọn số phiên bản cao nhất, mới nhất, hay phiên bản thư viện được tải về gần đây nhất. Phán đoán phải dựa vào **đồ thị dependency đã được phân giải**, không phải nhìn riêng từng số version.

Bài này giới hạn ở **version mediation trong dependency graph của project**, không phải cách chọn phiên bản Maven Compiler Plugin, plugin repository hoặc cách Maven tự tải Maven runtime.

## 2. Ba thuật ngữ bắt buộc phải phân biệt

### 2.1. Dependency trực tiếp (direct dependency)

Là dependency được khai báo trong `<project><dependencies>` của POM project hiện tại:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>lib-a</artifactId>
        <version>1.0</version>
    </dependency>
</dependencies>
```

Đây chỉ là **đoạn POM minh họa**. Nếu `lib-a` được khai báo trực tiếp, khoảng cách từ `app` đến `lib-a` là **một cạnh**, hay **độ sâu 1**.

### 2.2. Dependency bắc cầu (transitive dependency)

Nếu `lib-a` cũng phụ thuộc `shared-utils`, project app có thể nhận `shared-utils` mà không tự khai báo:

```text
app                  độ sâu 0
└── lib-a:1.0        độ sâu 1
    └── shared-utils:1.0   độ sâu 2
```

Đường đi đến `shared-utils` có hai cạnh: `app → lib-a → shared-utils`. Maven đọc các POM liên quan để xây dựng cây; nội dung thực sự được đưa lên classpath còn phụ thuộc `scope`, `optional`, `exclusions` và những quy tắc Maven khác.

### 2.3. Dependency mediation (phân xử phiên bản)

Khi một artifact có nhiều phiên bản được yêu cầu qua nhiều đường, Maven phân xử để chọn phiên bản cho dependency trong ngữ cảnh đó. Ví dụ cùng `groupId/artifactId/type/classifier` nhưng có version khác nhau thì có thể tạo một cuộc xung đột version. Đừng nhầm **artifact khác classifier** hoặc **khác loại đóng gói** với hai version của cùng một biến thể.

Với dependency JAR thông thường, cách nói ngắn gọn “cùng `groupId:artifactId` khác version” đã đủ cho phần lớn ví dụ nhập môn.

## 3. Quy tắc số 1 — đường dẫn gần nhất thắng

Xét một project tên `A`:

```text
A
├── B:1.0
│   └── C:1.0
│       └── D:2.0
└── E:1.0
    └── D:1.0
```

Có hai đường từ `A` tới `D`:

| Đường đi | Số cạnh từ A tới D | Phiên bản D được đường đó yêu cầu |
| --- | ---: | --- |
| `A → B → C → D` | 3 | `2.0` |
| `A → E → D` | 2 | `1.0` |

**Kết quả mediation: `D:1.0` thắng**, vì gần `A` hơn: độ sâu 2 nhỏ hơn 3. Số phiên bản `2.0` cao hơn không giúp nó thắng. Việc `B` được khai báo trước `E` cũng không giúp đường dài hơn thắng: **độ sâu được xét trước, thứ tự chỉ là tiêu chí khi hòa**.

Quy tắc này thường được gọi là **nearest wins** hoặc **nearest definition** trong tài liệu Apache Maven.

### Đếm độ sâu thế nào?

- Project gốc đang phân giải: độ sâu 0.
- Dependency được khai báo trực tiếp ở gốc: độ sâu 1.
- Dependency của dependency trực tiếp: độ sâu 2.
- Dependency qua ba bước: độ sâu 3.
- So sánh đến **cùng artifact cần phân xử**, không so tổng số module hay chiều dài file POM.

Lưu ý: “gần nhất” là **gần trên đồ thị dependency**, không phải gần về đường dẫn thư mục trên đĩa, cấu trúc package Java, hay vị trí Maven repository. Một dependency trong module con không tự có độ sâu 1 trong mọi project khác nếu không được khai báo trực tiếp.

## 4. Quy tắc số 2 — cùng độ sâu thì khai báo trước thắng

Xét một đồ thị khác:

```text
A
├── B:1.0                 <- khai báo thứ nhất trong A
│   └── D:1.0             <- độ sâu 2
└── E:1.0                 <- khai báo thứ hai trong A
    └── D:2.0             <- độ sâu 2
```

Hai phiên bản `D` đều ở **độ sâu 2**. Không thể chọn bằng tiêu chí “gần hơn” vì hòa nhau. Maven sử dụng **thứ tự khai báo** để phân xử: nhánh được đưa vào trước trong thứ tự dependency tương ứng sẽ có lợi thế.

Trong sơ đồ này, `B` đứng trước `E` trong `<dependencies>` của `A`, nên **`D:1.0` được chọn**.

Nếu **chỉ đảo thứ tự hai dependency trực tiếp trong POM của A**:

```text
A
├── E:1.0                 <- nay đứng thứ nhất
│   └── D:2.0             <- độ sâu 2
└── B:1.0                 <- nay đứng thứ hai
    └── D:1.0             <- độ sâu 2
```

thì **`D:2.0` được chọn**, giả sử những đường còn lại, scope, exclusions và dependency management không tạo thay đổi khác.

Đây là lý do thứ tự các thẻ `<dependency>` trong `pom.xml` đôi khi **có thể thay đổi phiên bản được phân giải**, dù cả hai phiên bản của D đều tồn tại trong cùng repository.

**Không hiểu nhầm rằng “dependency nằm trên cùng một dòng XML” hoặc “tên đứng trước theo alphabet” được ưu tiên.** Điều được xét là **thứ tự khai báo/phân giải** khi độ sâu của các đường cạnh tranh bằng nhau.

### Minh họa bằng các đoạn XML

POM A với B trước E:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>lib-b</artifactId>
        <version>1.0</version>
    </dependency>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>lib-e</artifactId>
        <version>1.0</version>
    </dependency>
</dependencies>
```

Đây là **đoạn minh họa**, không phải toàn bộ POM và không khẳng định `lib-b/lib-e` đã được xuất bản. Giả định `lib-b` kéo `shared-d:1.0`, còn `lib-e` kéo `shared-d:2.0` ở cùng độ sâu, phiên bản dưới nhánh `lib-b` sẽ thắng. Đảo vị trí hai khối dependency thì kết quả có thể đảo theo.

Một dự án lớn có thể còn nhiều nhánh trung gian và inherited dependency; lúc đó **không nên suy ra kết quả chỉ từ thứ tự của hai dòng trong một POM**. Phải xem graph thực tế bằng công cụ Maven.

## 5. Tại sao không nên trông chờ “version mới nhất thắng”?

Maven **không tự dùng** công thức:

```text
selectedVersion = max(allCandidateVersions)
```

Ví dụ:
- B yêu cầu D phiên bản `5.0`, cách A ba cạnh.
- E yêu cầu D phiên bản `4.0`, cách A hai cạnh.
- Maven chọn `4.0` theo nearest definition, dù `5.0` có version lớn hơn.

Với hai đường có cùng độ sâu, phiên bản thấp hơn vẫn có thể thắng chỉ vì nhánh của nó được khai báo trước. Ngoài ra, Maven không dùng thứ tự tải về trong local repository hay “file JAR vừa xuất hiện” làm trọng tài cho tie.

Điều này ảnh hưởng tới:
- **Tính tương thích API**: code có thể biên dịch với một version nhưng runtime/classpath lại nhận version khác dự định nếu cấu hình thay đổi.
- **An toàn cập nhật**: nâng version một thư viện trực tiếp có thể làm thay đổi những transitive dependency của nó, tạo xung đột mới.
- **Khả năng tái lập CI**: thêm hoặc đảo dependency, thay BOM/parent, thay scope đều có thể làm kết quả dependency graph khác.
- **Bảo trì**: nếu module đang dùng trực tiếp một API của thư viện bắc cầu nhưng không khai báo dependency đó, project trở nên phụ thuộc vào cấu trúc nội bộ của thư viện trung gian.

**Khuyến nghị của Apache Maven:** nếu source của project **sử dụng trực tiếp** API của thư viện nào, hãy khai báo dependency đó một cách trực tiếp trong POM thay vì mãi dựa vào phụ thuộc bắc cầu.

## 6. Ví dụ thực tế có thể kiểm chứng bằng Apache Commons

Ta dùng các version đã phát hành và POM của chúng trên Maven Central:

- `org.apache.commons:commons-configuration2:2.10.1` có dependency trực tiếp tới `org.apache.commons:commons-lang3:3.14.0`.
- `org.apache.commons:commons-text:1.11.0` có dependency trực tiếp tới `org.apache.commons:commons-lang3:3.13.0`.

Hai nhánh này cùng dẫn đến **commons-lang3**, nhưng yêu cầu **hai phiên bản khác nhau**.

Sơ đồ của ứng dụng thử nghiệm khi khai báo `commons-configuration2` trước `commons-text`:

```text
mediation-demo
├── commons-configuration2:2.10.1   <- dependency trực tiếp #1
│   ├── commons-lang3:3.14.0        <- độ sâu 2
│   └── commons-text:1.11.0         <- còn có đường bắc cầu khác
│       └── commons-lang3:3.13.0    <- độ sâu 3
└── commons-text:1.11.0             <- dependency trực tiếp #2
    └── commons-lang3:3.13.0        <- độ sâu 2
```

Đây là **sơ đồ khái niệm của các đường phụ thuộc được khai báo**, chưa phải bản in nguyên văn của `dependency:tree` sau khi Maven đã cắt các nhánh trùng hoặc bị conflict. Trong cây phân giải thực, một số node có thể bị rút gọn hoặc bỏ qua do trùng artifact.

Hai đường cạnh tranh gần nhất đến `commons-lang3` đều có độ sâu 2:

- nhánh `commons-configuration2` đưa ra `3.14.0`;
- nhánh `commons-text` đưa ra `3.13.0`.

Với thứ tự dependency trực tiếp trên, **Maven dự kiến chọn `commons-lang3:3.14.0` theo quy tắc khai báo trước**.

Khi đảo hai dependency trực tiếp (commons-text trước, configuration2 sau), kết quả dự kiến là `commons-lang3:3.13.0`. Hai version là các artifact có thật; tuy nhiên **khả năng tương thích runtime của tổ hợp phụ thuộc không được bảo đảm chỉ bởi quy tắc mediation**. Bài thực hành này nhằm quan sát version resolution, không khuyến nghị hạ phiên bản thư viện trong sản phẩm.

## 7. Tạo project Java 17 thực hành: trường hợp cùng độ sâu

Tạo hai file:

```text
mediation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/mediation/App.java
```

### 7.1. pom.xml đầy đủ — configuration2 trước, text sau

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>mediation-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-configuration2</artifactId>
            <version>2.10.1</version>
        </dependency>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-text</artifactId>
            <version>1.11.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **POM hoàn chỉnh** cho project JAR Java 17. Hai dependency có scope mặc định `compile` nên Maven sẽ lấy POM/artifact và giải quyết các transitive dependencies phù hợp. Chúng được dùng để **tạo xung đột minh họa**, không phải để ứng dụng cần gọi API của cả hai.

### 7.2. src/main/java/com/example/mediation/App.java

```java
package com.example.mediation;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Maven dependency mediation demo");
    }
}
```

Mã Java 17 có thể chạy độc lập vì không gọi các lớp Apache Commons ở runtime. Điều này có chủ đích: bài tập đo **kết quả phiên bản Maven giải quyết** qua `dependency:tree`, không phải kiểm tra API của Commons Configuration/Text khi một transitive dependency bị hạ phiên bản.

### 7.3. Chạy build và quan sát

Tại thư mục `mediation-demo` có `pom.xml`:

```bash
mvn -version
mvn -B -ntp clean package
java -cp target/classes com.example.mediation.App
```

Nếu môi trường có JDK 17+ và Maven tải được các plugin/artifact, kết quả build thông thường là `target/mediation-demo-1.0.0.jar`. **Stdout chính xác** của riêng lệnh `java` cuối cùng:

```text
Maven dependency mediation demo
```

Không nhầm stdout chương trình với log Maven của `clean package`. Để biết Maven chọn version nào, **không nhìn vào dòng Java trên** mà chạy dependency tree.

### 7.4. Xem dependency tree bằng goal đã ghim phiên bản

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
```

Để chỉ tập trung vào `commons-lang3` và các đường dẫn liên quan:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -Dincludes=org.apache.commons:commons-lang3
```

Để quan sát cả node bị bỏ qua vì conflict trong phiên bản Dependency Plugin có hỗ trợ `verbose`:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -Dverbose=true -Dincludes=org.apache.commons:commons-lang3
```

Trong bản hiển thị giản lược, hãy tìm một dependency có tọa độ tương ứng:

```text
org.apache.commons:commons-lang3:jar:3.14.0:compile
```

Đó là **dòng định danh artifact dự kiến được chọn** với POM ở mục 7.1; phần indentation, prefix cây và các dòng `omitted for conflict with ...` phụ thuộc vào chế độ và phiên bản plugin. **Đừng coi dòng trên là toàn bộ stdout Maven**.

Nếu cần lưu báo cáo để so sánh trước/sau, Dependency Plugin hỗ trợ:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -DoutputFile=tree-config-first.txt
```

Sau lệnh, đọc file `tree-config-first.txt`, tìm các mục liên quan `commons-lang3` và nhánh cha chứa nó.

## 8. Thí nghiệm thay đổi thứ tự để thấy tie-break

Giữ nguyên groupId/artifactId/version và các phần khác. **Chỉ hoán đổi vị trí hai khối `<dependency>`** trong `<dependencies>` của POM để `commons-text` đứng trước `commons-configuration2`:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-text</artifactId>
        <version>1.11.0</version>
    </dependency>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-configuration2</artifactId>
        <version>2.10.1</version>
    </dependency>
</dependencies>
```

Đây là **đoạn thay thế duy nhất** cho `<dependencies>` trong POM mục 7.1, không phải một file POM độc lập. Đừng thêm cả hai khối mới phía sau khối cũ: nếu làm vậy sẽ có khai báo duplicate cho cùng artifact và bài thực hành mất ý nghĩa.

Chạy lại:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -Dverbose=true -Dincludes=org.apache.commons:commons-lang3
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -DoutputFile=tree-text-first.txt
```

Kết quả dự kiến bây giờ chọn:

```text
org.apache.commons:commons-lang3:jar:3.13.0:compile
```

**Giải thích:** cả hai nhánh yêu cầu `commons-lang3` tại độ sâu 2, nhưng `commons-text` được khai báo trước nên yêu cầu `3.13.0` có lợi thế. Đây là biểu hiện của **first declaration wins when depth is equal**.

Để đối chiếu công bằng, thực hiện hai lần với **cùng Maven version, cùng settings/repository và cùng POM ngoại trừ thứ tự**. Các lệnh này có thể tải về artifact chưa có cache; thông tin download không phải bằng chứng rằng một version đã được chọn.

Nếu plugin hiển thị khác dự kiến, kiểm tra: bạn đã sửa đúng `pom.xml` chưa; có `dependencyManagement`, profile, Maven extension hay dependency bổ sung không; các version trên Maven Central có phân giải được trong mạng hiện tại không; và kết quả thực tế trong cây là gì. **Coi dependency tree là bằng chứng chính**, không cố ép dữ liệu phù hợp với sơ đồ.

## 9. Thí nghiệm về độ gần nhất: thêm dependency trực tiếp

Ở mục 8, `commons-lang3` chỉ xuất hiện bắc cầu, ở độ sâu 2. Để chủ động chọn phiên bản, thêm dependency **trực tiếp** cho `commons-lang3` tại POM project:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Chèn đoạn này **bên trong `<dependencies>`** của POM, bên cạnh các dependency trực tiếp hiện có. Không chèn ngoài `<dependencies>`.

Khi đó các đường cạnh tranh trở thành:

```text
mediation-demo
├── commons-lang3:3.14.0             <- độ sâu 1 (trực tiếp)
├── commons-text:1.11.0
│   └── commons-lang3:3.13.0         <- độ sâu 2
└── commons-configuration2:2.10.1
    └── commons-lang3:3.14.0         <- độ sâu 2
```

**Kết quả mong đợi: `commons-lang3:3.14.0` thắng do độ sâu 1 nhỏ hơn 2.** Tại thời điểm này, thứ tự `commons-text` với `commons-configuration2` không còn là yếu tố tie-break để chọn version của `commons-lang3`, vì app đã yêu cầu trực tiếp phiên bản 3.14.0.

Chạy:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -Dverbose=true -Dincludes=org.apache.commons:commons-lang3
```

Tìm node `org.apache.commons:commons-lang3:jar:3.14.0:compile`. Nếu `verbose` hiển thị các nhánh bị loại, chúng thường có ghi chú conflict/duplicate tương ứng.

**Lưu ý thiết kế:** khai báo một dependency trực tiếp chỉ để điều chỉnh version là một biện pháp dễ hiểu nhưng có thể làm tăng phạm vi classpath. Nếu ứng dụng không dùng API trực tiếp, hệ thống nhiều module thường nên quản lý version tập trung trong `dependencyManagement` để tránh lặp lại.

## 10. Cách quản lý version rõ ràng bằng dependencyManagement

Khi nhiều module cùng cần một phiên bản cố định, có thể khai báo trong parent POM hoặc POM project:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn cấu hình** phải nằm trực tiếp dưới `<project>` của POM hợp lệ. Với POM thực hành mục 7.1, thêm đoạn này trước `<dependencies>` hoặc ở vị trí phù hợp trong POM; không tạo hai khối `<dependencyManagement>` không nhất quán.

Khác với `<dependencies>`:

- `dependencyManagement` xác định version/cấu hình **được quản lý** cho dependency phù hợp khi Maven gặp nó;
- chỉ đặt một artifact trong `dependencyManagement` **không tự thêm artifact lên classpath**;
- khi một transitive dependency matching được gặp, cấu hình quản lý từ project hiện tại/parent có thể tác động tới version được phân giải, trước khi đơn thuần dựa vào nearest/tie-break;
- một direct dependency đã khai báo version tường minh là chuyện khác: cần hiểu thứ tự ưu tiên giữa khai báo trực tiếp, management và POM thực tế, không giả định management âm thầm ghi đè tất cả.

Trong ví dụ hai nhánh Commons, management `commons-lang3:3.14.0` giúp project chủ động thống nhất version thay vì tình cờ lệ thuộc thứ tự hai dependency direct. Hãy kiểm tra bằng `dependency:tree` sau mỗi thay đổi.

### BOM và parent

Một **BOM (Bill of Materials)** được nhập qua `<dependencyManagement>` có thể cung cấp version thống nhất cho nhiều thư viện. Parent POM cũng có thể kế thừa dependency management cho module con. Những cơ chế đó thường phù hợp hơn việc âm thầm dựa vào “first declaration” ở mỗi module.

Ví dụ nhập BOM theo cấu trúc Maven (tọa độ ở đây chỉ là **dạng minh họa**, không phải BOM được khẳng định có thật):

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

`scope=import` chỉ hợp lệ với kiểu `pom` trong `dependencyManagement`; đây **không phải dependency runtime của app**. Sau import, project sử dụng version được quản lý theo quy tắc Maven. Để hiểu version cụ thể đến từ đâu, dùng `help:effective-pom` kết hợp `dependency:tree`.

## 11. Kiểm tra đúng kết quả bằng Maven Dependency Plugin

Goal chính:

```bash
mvn dependency:tree
```

Lệnh ngắn thường hoạt động khi Maven phân giải được prefix `dependency`. Trong môi trường cần chốt phiên bản công cụ, dùng đầy đủ:

```bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree
```

Các tùy chọn hữu ích:

| Tham số | Mục đích |
| --- | --- |
| `-Dincludes=org.apache.commons:commons-lang3` | Chỉ hiện các đường liên quan artifact cần phân tích |
| `-Dverbose=true` | Hiển thị cả node bị lược bỏ trong định dạng mà plugin hỗ trợ |
| `-DoutputFile=dependency-tree.txt` | Ghi cây dependency ra file |
| `-DoutputType=json` | Xuất dạng JSON trong các bản Dependency Plugin hỗ trợ (từ 3.7.0) |
| `-Dscope=compile` | Lọc theo scope khi phân tích |
| `-Dexcludes=...` | Lọc các artifact không cần hiển thị trong báo cáo |

Ví dụ dùng plugin 3.10.0 để lưu kết quả dễ so sánh:

```bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -Dverbose=true -DoutputFile=dependency-tree.txt
```

Một số định dạng kết quả có thể trông tương tự:

```text
[INFO] +- org.apache.commons:commons-configuration2:jar:2.10.1:compile
[INFO] |  \- org.apache.commons:commons-lang3:jar:3.14.0:compile
[INFO] \- org.apache.commons:commons-text:jar:1.11.0:compile
[INFO]    \- (org.apache.commons:commons-lang3:jar:3.13.0:compile - omitted for conflict with 3.14.0)
```

Đây là **ví dụ log rút gọn nhằm chỉ ra cách đọc**, không phải bản sao nguyên văn từ một lượt chạy; cây thật có thể còn các dependency khác, nhánh duplicate và cách hiển thị khác. Dấu `omitted for conflict with ...` cho biết ứng viên bị loại do version khác đã thắng. Dấu `omitted for duplicate` là trường hợp node giống nhau bị gộp, không phải chứng cứ có version conflict mới.

### Cách đọc cây đúng thứ tự

1. Xác định artifact gốc có đúng `groupId:artifactId:version` của project không.
2. Tìm toàn bộ đường ứng viên của dependency đang quan tâm; khi bình thường chỉ thấy phiên bản được chọn, hãy dùng `verbose` nếu cần xem node bị loại.
3. Đếm độ sâu từ root đến artifact ở từng đường **trước khi** xem thứ tự.
4. Nếu độ sâu khác nhau: áp dụng **nearest wins**.
5. Nếu độ sâu bằng nhau: xem thứ tự dependency và cách graph được hình thành.
6. Kiểm tra `dependencyManagement`, parent/BOM và các yếu tố hạn chế transitive (scope, exclusions, optional).
7. Ghi lại phiên bản thắng, kiểm tra API/test, rồi chỉ chốt bản dùng trong CI khi tổ hợp thực sự tương thích.

Không suy version được chọn từ một dòng “Downloading from ...” vì Maven có thể tải POM/metadata của ứng viên khác rồi vẫn loại artifact đó khỏi resolved graph.

## 12. Vì sao dependencyManagement và scope có thể làm kết quả khác sơ đồ?

Hai quy tắc nearest/tie-break **không hoạt động trên một đồ thị bất biến do người đọc tự tưởng tượng**. Maven cần dựng graph từ các POM thực tế rồi loại các dependency không được truyền theo đúng quy tắc.

### 12.1. Scope

`scope=compile` thường được đưa vào classpath compile và truyền qua các dependency phù hợp. `scope=test` không truyền bắc cầu như compile. `provided` có giới hạn riêng. Một nhánh trong POM thư viện có thể không xuất hiện như một nhánh compile trong project gốc, nên không thể chỉ dựa vào đoạn XML của thư viện trung gian mà khẳng định nó đang cạnh tranh.

### 12.2. Optional

Một dependency được đánh dấu `<optional>true</optional>` ở một thư viện thường không được truyền như dependency bắt buộc xuống project tiêu thụ. Nếu project tiêu thụ cần API đó, hãy khai báo trực tiếp.

### 12.3. Exclusions

`<exclusions>` có thể loại một transitive dependency trên **một đường phụ thuộc cụ thể**. Khi một nhánh đã bị loại, “ứng viên” của nhánh đó không còn tham gia mediation theo cách ban đầu. Exclusion không tự thêm version thay thế, nên có thể gây `ClassNotFoundException` nếu application vẫn cần thư viện đã loại.

Ví dụ chỉ minh họa cấu trúc XML:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>lib-b</artifactId>
    <version>1.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>shared-d</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Đoạn trên không chỉ định version trong `<exclusion>`: Maven exclusions nhắm tới nhóm/định danh artifact được loại trong đường đó, không đơn giản là “loại version 1.0 để tự chuyển sang 2.0”.

### 12.4. Parent/BOM và dependencyManagement

Một version được **quản lý** từ parent/BOM có thể được áp dụng lên transitive dependencies trước khi bạn quan sát cây cuối cùng. Bởi vậy, nếu sơ đồ lý thuyết nói “3.13.0 phải thắng do khai báo trước” nhưng dependency tree hiện `3.14.0`, hãy kiểm tra xem project đã có management cho `commons-lang3` hay chưa.

## 13. Direct dependency và chuyện thay đổi thứ tự trong team

Có tình huống người phát triển thêm một dependency mới vào đầu `<dependencies>`. Dù không sửa version nào đang khai báo trực tiếp, bản mới có thể mang theo một **đường transitive cùng độ sâu** và gây thay đổi version thực tế.

Ví dụ:
- Trước đây project lấy `shared-utils:1.0` qua `lib-a`.
- Thêm `lib-b` lên trên, và `lib-b` cũng kéo `shared-utils:2.0` tại cùng độ sâu.
- Kết quả có thể chuyển sang `shared-utils:2.0` dù chưa trực tiếp chỉnh `shared-utils` trong POM.

Điều này dẫn tới bài học về **code review**:
- Thêm/reorder dependencies có thể là thay đổi hành vi build.
- Không nên sắp xếp alphabet mọi dependency bằng script mà không kiểm tra graph trước/sau.
- Nếu module thực sự dùng API của một transitive artifact, nên khai báo trực tiếp theo hướng dẫn Maven.
- Với tổ chức nhiều module, dùng parent/BOM để đồng bộ các version quan trọng.
- Khi nâng thư viện, chạy unit/integration tests vì mediation đúng không chứng minh API có tương thích binary/source.

**Đừng dùng “đổi thứ tự cho tới khi build xanh” làm chính sách version lâu dài.** Nếu một version bắt buộc, hãy thể hiện nó rõ trong POM hoặc version management rồi kiểm chứng.

## 14. Phân biệt các lỗi dễ gây hiểu sai

| Quan sát | Nhầm lẫn thường gặp | Cách xử lý đúng |
| --- | --- | --- |
| Maven chọn `D:1.0` dù một nhánh yêu cầu `D:2.0` | “Maven chọn bản cũ ngẫu nhiên” | Đếm độ sâu, kiểm tra nearest/tie |
| Sau khi đảo dependency, version đổi | “Thứ tự POM không quan trọng” | Kiểm tra tie ở cùng độ sâu và chốt version tường minh nếu cần |
| Thêm dependency trực tiếp, version đổi | “Repository ưu tiên file vừa tải” | Đường direct có độ sâu 1, thắng đường transitive sâu hơn |
| `dependency:tree` chỉ hiện một version | “Chỉ tồn tại một version trong tất cả POM” | Maven đã phân xử; dùng `verbose`/POM nguồn để xem candidate bị loại |
| Hai lần build khác nhau | “Maven chọn ngẫu nhiên” | So sánh POM, profile, parent/BOM, Maven/plugin version, settings, local repo |
| Một nhánh vắng trong tree | “Maven làm mất dependency” | Kiểm tra scope, optional, exclusions và đường trùng |
| Library chạy lỗi `NoSuchMethodError` | “Chắc Maven không tải dependency” | Có thể version thắng không phù hợp API; so runtime classpath và graph |
| `mvn help:effective-pom` có một version quản lý | “Đó là version runtime chắc chắn” | Effective POM là mô hình; dùng `dependency:tree` để xem graph đã resolve |
| Có hai `<dependency>` direct trùng GA khác version | “Maven sẽ tự dùng first declaration an toàn” | Không dùng duplicate dependency declaration; Maven có thể cảnh báo/lỗi model |
| Artifact khác classifier | “Đó là hai version cạnh tranh” | Xác định đúng type/classifier và dependency identity |
| Plugin runtime dùng version khác | “Nearest rule của ứng dụng sẽ giải quyết cả plugin dependency” | Plugin có graph/classloader riêng; xem plugin configuration |

Khi gặp lỗi runtime như `NoSuchMethodError`, `NoClassDefFoundError` hoặc `ClassNotFoundException`, không khẳng định ngay do mediation. Nhưng một bước chẩn đoán quan trọng là đối chiếu **version trên compile/test/runtime classpath** với version của thư viện yêu cầu API đó.

## 15. Quy trình kiểm tra trên CI và dự án đa module

Với project chỉ có một module:

```bash
mvn -B -ntp clean verify
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.10.0:tree -DoutputFile=dependency-tree.txt
```

Cách làm thực tế:

1. Lưu output dependency tree dưới dạng artifact của CI khi cần điều tra sự thay đổi version.
2. Nếu vừa nâng dependency, so sánh cây trước và sau; chú ý các node cùng GA nhưng version thay đổi.
3. Với thư viện được code sử dụng trực tiếp, khai báo dependency trực tiếp và khóa version phù hợp.
4. Dùng `dependencyManagement`/BOM cho version chung nếu nhiều module cần đồng bộ.
5. Chạy các bài test phù hợp; kết quả tree không thay thế kiểm thử tương thích.
6. Nếu muốn CI báo lỗi khi graph không hội tụ, đánh giá Maven Enforcer Plugin với rule **`dependencyConvergence`** hoặc **`requireUpperBoundDeps`** theo mục tiêu dự án.

Hai rule Enforcer có ý nghĩa khác nhau. `dependencyConvergence` kiểm tra sự nhất quán các version theo đường dependency; `requireUpperBoundDeps` kiểm tra ràng buộc về version được chọn so với các version yêu cầu. Không chỉ bật rule mà không hiểu hệ quả với dependency graph hiện tại.

Với reactor nhiều module:
- Từng module có **root dependency graph riêng**. Cùng một artifact có thể được chọn ở version khác trong các module nếu POM/management của chúng khác nhau.
- Khi `mvn dependency:tree` từ reactor root, công cụ có thể in nhiều project/module; đọc đúng phần module cần phân tích.
- Nếu cần khảo sát một module cụ thể, dùng `-pl` hoặc `-f` phù hợp cấu trúc project, chẳng hạn `mvn -pl :app dependency:tree` khi reactor có module `app`.
- Reactor build order và **độ sâu trong dependency graph** không phải một khái niệm; đừng lấy vị trí module trên log để quyết định version mediation.

Trong CI, một giải pháp bền vững không chỉ là “chạy được trên máy tôi” mà còn là **POM biểu đạt chính sách version và dependency tree có thể tái kiểm chứng**.

## 16. Câu hỏi tự kiểm tra

1. Trong đồ thị `A → B → C → D:2.0` và `A → E → D:1.0`, Maven chọn version D nào? Vì sao?
2. Trong đồ thị `A → B → D:1.0` và `A → E → D:2.0`, nếu B được khai báo trước E thì version nào thắng?
3. Nếu đổi thứ tự khai báo B/E nhưng một đường tới D sâu hơn đường còn lại, version có nhất thiết đổi không?
4. Vì sao quy tắc nearest không đồng nghĩa chọn phiên bản cao nhất?
5. Khi một project khai báo trực tiếp `commons-lang3:3.14.0`, vì sao nhánh transitive độ sâu 2 không còn thắng?
6. Vì sao `dependencyManagement` không tự thêm dependency vào classpath?
7. Dùng lệnh nào để xem version đã được Maven chọn và các nhánh bị loại vì conflict?
8. Tại sao `commons-configuration2:2.10.1` và `commons-text:1.11.0` phù hợp để minh họa tie-break giữa hai version `commons-lang3`?
9. Nếu build thành công nhưng runtime ném `NoSuchMethodError`, dependency tree có thể giúp điều tra điều gì?
10. Vì sao trong review một PR chỉ “đổi thứ tự dependencies”, vẫn nên chạy lại kiểm tra dependency graph?

**Tổng kết:** Maven ưu tiên phiên bản ở **đường phụ thuộc gần project nhất**; nếu hòa độ sâu thì **nhánh được khai báo trước thắng**. Đây là cơ chế phân xử mặc định, không phải chính sách chọn phiên bản mới nhất hay bảo đảm tương thích. Để build ổn định, hãy xem `dependency:tree`, khai báo trực tiếp thư viện sử dụng trực tiếp và quản lý version bằng parent/BOM khi cần.

## Tài liệu chính thức và POM gốc để kiểm chứng

- [Apache Maven — Introduction to the Dependency Mechanism (Dependency Mediation)](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Dependency Plugin — dependency:tree goal](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Apache Maven Dependency Plugin — Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html)
- [Apache Maven Enforcer Plugin — Dependency Convergence](https://maven.apache.org/enforcer/enforcer-rules/dependencyConvergence.html)
- [Apache Maven Enforcer Plugin — Require Upper Bound Dependencies](https://maven.apache.org/enforcer/enforcer-rules/requireUpperBoundDeps.html)
- [Apache Commons Configuration 2.10.1 — Published POM](https://central.sonatype.com/artifact/org.apache.commons/commons-configuration2/2.10.1)
- [Apache Commons Text 1.11.0 — Published POM](https://central.sonatype.com/artifact/org.apache.commons/commons-text/1.11.0)
