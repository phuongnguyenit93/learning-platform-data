# Quy ước thay cho cấu hình trong thiết kế dự án Maven

## 1. Ý tưởng cốt lõi

**Convention over Configuration (CoC)**, hay **quy ước thay cho cấu hình**, là nguyên tắc thiết kế: khi nhiều dự án làm cùng một việc theo một cách phổ biến, công cụ cung cấp sẵn cách đó làm mặc định. Người phát triển chỉ cần khai báo những điểm khác mặc định hoặc những thông tin thực sự riêng của dự án.

Maven áp dụng nguyên tắc này cho **cấu trúc thư mục, mô hình dự án, vòng đời build và việc gắn plugin vào các pha build**. Thay vì viết một chuỗi lệnh tùy chỉnh để tìm mã nguồn, biên dịch, chạy kiểm thử rồi đóng gói, một dự án theo quy ước có thể chạy các mục tiêu quen thuộc như **mvn test** hoặc **mvn package**.

CoC không có nghĩa là “không cần cấu hình”. Maven vẫn cần định danh dự án, các dependency, phiên bản công cụ phù hợp và mọi ngoại lệ có chủ đích. Mục tiêu là **giữ cấu hình ngắn, dễ đoán và đủ tường minh ở những điểm ảnh hưởng đến tính tái lập**.

## 2. Maven mặc định hiểu gì từ một POM tối thiểu?

Tệp **pom.xml** ở thư mục gốc mô tả Project Object Model. Với dự án độc lập đơn giản, một POM có thể bắt đầu như sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>maven-convention-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
</project>
```

Ba tọa độ **groupId:artifactId:version** xác định artifact. Vì không khai báo **packaging**, Maven dùng mặc định **jar**. Với kiểu đóng gói này, Maven có các phép gắn plugin mặc định theo lifecycle: xử lý resource, biên dịch Java, chạy test và tạo JAR ở những pha tương ứng.

POM tối thiểu trên **minh họa các mặc định**, chưa bảo đảm biên dịch đúng cho một phiên bản Java cụ thể hay chạy kiểm thử bằng một framework bất kỳ. Ví dụ thực hành ở mục 5 sẽ khai báo riêng Java 17 và bộ công cụ test.

## 3. Quy ước cấu trúc thư mục

```text
maven-convention-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/              # Mã nguồn ứng dụng
│   │   └── resources/         # Cấu hình, dữ liệu đi cùng ứng dụng
│   └── test/
│       ├── java/              # Mã nguồn kiểm thử
│       └── resources/         # Tài nguyên phục vụ kiểm thử
└── target/                    # Kết quả build; Maven tạo khi cần
```

Theo mặc định, Maven lấy mã Java ứng dụng từ **src/main/java**, mã test từ **src/test/java**, sao chép resource ứng dụng vào **target/classes** và resource kiểm thử vào **target/test-classes**. Mã biên dịch chính cũng nằm trong **target/classes**; mã test biên dịch vào **target/test-classes**. Artifact đóng gói thường xuất hiện trong **target/**.

Việc đặt lớp Java theo package cũng quan trọng. Chẳng hạn, lớp **vn.example.Greeting** nằm tại **src/main/java/vn/example/Greeting.java**. Maven không cần khai báo đường dẫn này trong POM khi dự án theo quy ước.

**Lợi ích trong thiết kế dự án:** người mới mở repository có thể tìm mã ứng dụng, test và resource ngay; IDE, CI và các plugin Maven phổ biến cũng nhận diện cấu trúc theo cách nhất quán. Thư mục **target/** là kết quả sinh ra từ build, thông thường được thêm vào **.gitignore**.

## 4. Vòng đời build: gọi pha, Maven thực hiện những bước trước đó

Maven có ba lifecycle dựng sẵn thường được nhắc đến: **default** (xây dựng dự án), **clean** (dọn kết quả build) và **site** (tạo trang thông tin dự án). Mỗi lifecycle gồm các pha có thứ tự; chạy một pha sẽ chạy các pha đứng trước nó **trong cùng lifecycle**.

| Lệnh / pha | Ý nghĩa thực tế |
| --- | --- |
| **mvn validate** | Kiểm tra thông tin và cấu trúc dự án cơ bản. |
| **mvn compile** | Chạy các pha trước **compile**, xử lý resource và biên dịch nguồn chính theo binding của kiểu dự án. |
| **mvn test** | Biên dịch mã test rồi thực thi test được plugin test nhận diện; chưa đóng gói JAR. |
| **mvn package** | Chạy đến pha **package**, bao gồm bước test trước đó; với packaging **jar** thì tạo tệp JAR. |
| **mvn verify** | Chạy đến **verify**, thực thi các kiểm tra được gắn vào các pha liên quan; không tự xuất hiện mọi loại kiểm tra nếu chưa cấu hình plugin tương ứng. |
| **mvn install** | Chạy đến **install**, đưa artifact vào repository Maven cục bộ để dự án khác có thể dùng. |
| **mvn deploy** | Chạy đến **deploy**; việc xuất bản lên repository từ xa cần cấu hình địa chỉ, quyền truy cập phù hợp. |
| **mvn clean package** | Chạy pha **clean** của lifecycle clean, sau đó chạy tới **package** của lifecycle default. |

**Pha (phase) khác goal của plugin.** Ví dụ **package** là pha; **jar:jar** là một goal của Maven JAR Plugin. Với dự án có packaging **jar**, các goal được Maven bind mặc định vào những pha như **resources**, **compile**, **test** và **package**. Đổi packaging thành **war** hoặc **pom** làm thay đổi hành vi/binding thích hợp; không thể giả định mọi dự án luôn tạo JAR.

Maven tuân theo quy ước **về thứ tự và cách gọi build**, còn kết quả cụ thể phụ thuộc vào POM hiệu lực, packaging, plugin, phiên bản, cấu hình profile và môi trường thực thi.

## 5. Ví dụ đầy đủ: dự án Java 17 có kiểm thử

Mục tiêu: tạo một ứng dụng đơn giản và một bài test bằng JUnit Jupiter. Ta **giữ nguyên các đường dẫn mặc định**, nhưng khai báo những thứ Maven không thể suy ra: Java 17, dependency JUnit và phiên bản plugin cần thiết để biên dịch/chạy JUnit 5 ổn định.

**Bước 1 — pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>maven-convention-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Không có **sourceDirectory**, **testSourceDirectory**, **outputDirectory** hay cấu hình thủ công cho goal **jar:jar**: Maven dùng quy ước. Thuộc tính **maven.compiler.release** yêu cầu biên dịch theo API/bytecode của Java 17; môi trường chạy Maven phải có JDK hỗ trợ release 17. Dependency JUnit chỉ cần trong scope **test**, còn Maven Surefire Plugin phiên bản được nêu hỗ trợ chạy test JUnit Platform.

**Bước 2 — src/main/java/vn/example/Greeting.java**

```java
package vn.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(message("Maven"));
    }
}
```

**Bước 3 — src/test/java/vn/example/GreetingTest.java**

```java
package vn.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Xin chào, Maven!", Greeting.message("Maven"));
    }
}
```

Tên **GreetingTest** phù hợp kiểu tên test mặc định mà Surefire nhận diện. Chạy từ thư mục chứa POM, với Maven và JDK 17+ đã cài:

```bash
mvn clean verify
java -cp target/maven-convention-demo-1.0.0-SNAPSHOT.jar vn.example.Greeting
```

Lệnh Maven đầu tiên dọn thư mục build, biên dịch nguồn, biên dịch/chạy test và tạo JAR; **verify** kết thúc thành công khi các bước đã cấu hình đều đạt. Lệnh Java thứ hai chạy lớp có phương thức **main** bên trong JAR. **Đầu ra của riêng lệnh Java thứ hai** là:

```text
Xin chào, Maven!
```

Không dùng **java -jar** cho ví dụ này: JAR mặc định chưa được khai báo thuộc tính **Main-Class** trong manifest. Muốn khởi chạy bằng **java -jar**, cần cấu hình manifest/plugin hoặc cách đóng gói phù hợp.

## 6. Khi nào giữ mặc định, khi nào cấu hình rõ ràng?

| Thành phần | Quy ước Maven | Khi cần cấu hình |
| --- | --- | --- |
| Mã nguồn và test | **src/main/java**, **src/test/java** | Dự án legacy buộc phải giữ layout khác; cân nhắc chuyển về chuẩn nếu có thể. |
| Resource | **src/main/resources**, **src/test/resources** | Cần lọc token, chọn resource bổ sung hoặc xử lý đặc biệt. |
| Packaging | **jar** khi bỏ trống | Dự án web cần **war**, dự án aggregator/parent thường dùng **pom**. |
| Kết quả build | Thư mục **target/**, tên artifact dựa vào tọa độ | Có yêu cầu đặt tên/đường dẫn đầu ra khác. |
| Java release | Không suy ra chắc chắn phiên bản Java mong muốn từ JDK đang cài | Khai báo release/toolchain phù hợp với sản phẩm và CI. |
| Dependency | Maven có cơ chế tải, giải quyết dependency bắc cầu | Phải khai báo dependency trực tiếp, phiên bản/quản lý phiên bản và scope cần thiết. |
| Kiểm thử | Các pha và plugin test có quy ước nhận diện | Cần framework, plugin hỗ trợ, test integration hoặc chính sách coverage. |
| Phân phối artifact | **install** vào repository cục bộ | **deploy** lên repository tổ chức cần cấu hình và thông tin xác thực. |

Một dự án có thể **cấu hình đúng mức** mà vẫn theo CoC. Ví dụ nêu trên chỉ khai báo Java release, JUnit và phiên bản plugin; phần lớn quá trình build vẫn được suy ra từ quy ước.

Trong dự án nhiều module, POM cha có thể quản lý phiên bản dependency và plugin. **dependencyManagement** giúp quy định phiên bản/thông số cho dependency được khai báo ở nơi sử dụng; nó không tự thêm dependency vào classpath của mọi module. **pluginManagement** cung cấp phiên bản/cấu hình khi plugin được dùng hoặc bind vào lifecycle; một goal tùy chỉnh không tự chạy chỉ vì xuất hiện trong pluginManagement. Các module con vẫn nên theo bố cục **src/main** và **src/test** khi không có lý do khác.

## 7. Những nhầm lẫn thường gặp

1. **Để mã nguồn ở src/ hoặc source/ rồi thắc mắc Maven không biên dịch.** Maven mặc định tìm **src/main/java**. Giải pháp ưu tiên là đặt đúng thư mục; chỉ sửa **build/sourceDirectory** khi thực sự phải giữ cấu trúc cũ.
2. **Tưởng Maven tự chọn Java release chuẩn cho mọi máy.** Phiên bản JDK chạy Maven và phiên bản bytecode cần xuất ra là hai quyết định khác nhau. Khai báo release tương thích, quản lý plugin và kiểm tra trên CI.
3. **Tưởng mvn test tương đương mvn package.** Pha test chạy trước package, nhưng gọi **test** không tự chạy các pha sau nó.
4. **Tưởng mọi test Java đều được chạy chỉ vì nằm trong thư mục test.** Cần framework/engine phù hợp, test class có tên được plugin nhận diện và Surefire/thiết lập tương thích. Các bài integration test có thể cần Failsafe cùng binding riêng.
5. **Nhầm dependencyManagement với dependencies.** Khai báo quản lý phiên bản không tương đương khai báo sử dụng thư viện; tương tự, mã nguồn import một package không khiến Maven tự tải dependency.
6. **Nhầm JAR mặc định với executable/fat JAR.** Đóng gói thành JAR không tự thêm **Main-Class** và không tự gom toàn bộ thư viện phụ thuộc. Muốn chạy trực tiếp hoặc tạo uber JAR phải có cấu hình đóng gói tương ứng.
7. **Sao chép cấu hình plugin mặc định sang mọi POM.** Việc lặp các cấu hình đường dẫn, execution và output giống mặc định khiến dự án khó duy trì, nhất là khi đổi phiên bản Maven/plugin. Nhưng những phiên bản plugin, yêu cầu release hoặc kiểm tra bắt buộc vẫn nên được kiểm soát tường minh.
8. **Đặt bí mật truy cập repository vào POM.** Thông tin xác thực thường đặt trong **settings.xml** của môi trường/người dùng hoặc qua cơ chế quản lý secret của CI; POM không phải nơi lưu mật khẩu.

## 8. Cách kiểm tra Maven đang dùng những mặc định nào

Thay vì phỏng đoán vì sao Maven chạy một goal hoặc chọn một giá trị, xem **effective POM**: mô hình sau khi tổng hợp POM dự án, kế thừa từ parent/Super POM và các profile đang áp dụng.

```bash
mvn help:effective-pom
mvn help:effective-settings
mvn -X test
```

- **help:effective-pom** giúp đối chiếu cấu hình POM sau khi hợp nhất/kế thừa.
- **help:effective-settings** giúp xem settings hiệu lực (cẩn trọng khi chia sẻ output vì cấu hình môi trường có thể nhạy cảm).
- **-X** bật log chẩn đoán để kiểm tra plugin/goal thực sự được chạy; log có thể dài và có thông tin môi trường.

Khi công cụ hoặc cách đóng gói thay đổi, hãy xác nhận lại hành vi thực tế của lifecycle và các phiên bản plugin. Với nhóm phát triển, có thể cung cấp **Maven Wrapper** trong repository để thống nhất phiên bản Maven chạy trên máy cá nhân và CI; wrapper phải được bổ sung vào dự án, không tự xuất hiện từ POM tối thiểu.

## 9. Áp dụng CoC khi thiết kế một dự án Maven mới

Hãy bắt đầu bằng **pom.xml** với tọa độ rõ ràng, chọn packaging đúng mục tiêu và tạo thư mục nguồn/test chuẩn. Tiếp theo, khai báo dependency, phiên bản Java, plugin/kiểm thử và các yêu cầu về tính tái lập; giữ nguyên những mặc định phù hợp, chỉ thêm cấu hình cho nhu cầu có lý do cụ thể. Chạy **mvn clean verify** trong CI để xác nhận toàn bộ đường đi từ biên dịch đến kiểm thử và đóng gói.

Khi tiếp nhận một dự án cũ, đối chiếu từng tùy biến POM với quy ước Maven: nếu cấu hình chỉ lặp mặc định thì có thể đơn giản hóa; nếu phản ánh yêu cầu nghiệp vụ/kỹ thuật thật sự thì giữ lại và giải thích ngắn gọn. Mục tiêu cuối cùng là **một dự án mà người khác đoán đúng được cách build từ cấu trúc và POM**, đồng thời mọi ngoại lệ quan trọng đều hiện diện rõ ràng.
