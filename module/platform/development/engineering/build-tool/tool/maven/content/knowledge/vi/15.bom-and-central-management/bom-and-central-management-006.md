# Thứ tự ưu tiên khi nhiều BOM quản lý cùng một thư viện trong Maven

## 1. Vì sao import nhiều BOM có thể làm version thay đổi?

Maven cho phép một project import nhiều **BOM (Bill of Materials)** để dùng chung bộ phiên bản thư viện của các nền tảng khác nhau: BOM của framework, BOM cho hạ tầng cloud, BOM nội bộ công ty hoặc BOM của các thư viện dùng chung. Khi hai BOM **cùng quản lý một artifact** nhưng đề xuất **hai version khác nhau**, Maven phải xác định version management nào có hiệu lực.

Ví dụ:

```text
consumer/pom.xml
  dependencyManagement
    1. import bom-alpha  -> commons-lang3:3.12.0
    2. import bom-beta   -> commons-lang3:3.14.0
```

Nếu consumer **không trực tiếp khai báo quản lý** `commons-lang3` và không có tác động từ parent/management khác, **BOM được import trước thắng**: kết quả là `commons-lang3:3.12.0`. Đổi import order để BOM beta đứng trước có thể làm version thành `3.14.0`.

Đây là **thứ tự ưu tiên của việc hợp nhất dependencyManagement khi import BOM**, không phải “Maven luôn chọn version lớn nhất”, không phải “BOM khai báo cuối ghi đè BOM trước”, cũng không phải quy tắc nearest-definition của transitive dependency graph.

Sau bài này, bạn sẽ:

1. Hiểu BOM, `<dependencyManagement>` và `<scope>import</scope>`.
2. Dự đoán kết quả nếu hai hoặc nhiều BOM có **managed entry trùng nhau**.
3. Phân biệt entry **đến từ BOM** và **khai báo management trực tiếp** trong consumer.
4. Hiểu vai trò của parent POM, import BOM lồng nhau, direct dependencies và dependency mediation.
5. Biết dùng `help:effective-pom` và `dependency:tree` để kiểm chứng bằng dữ liệu thực.
6. Thực hành với **hai BOM độc lập + ứng dụng Java 17** và các kịch bản đảo thứ tự, override version.
7. Tránh vòng parent/BOM và những thay đổi BOM làm hỏng compatibility ở runtime.

Ví dụ dùng Maven POM model 4.0.0 tương thích Maven 3.9.x, Java 17+. Maven 4 có thêm BOM packaging riêng trong model mới; không trộn cú pháp Maven 4 vào POM của ví dụ Maven 3.

## 2. BOM khác gì với dependency thông thường?

### 2.1. BOM quản lý phiên bản, không tự thêm thư viện vào classpath

BOM thông dụng trong Maven 3 là một POM có `<packaging>pom</packaging>` và danh sách `dependencyManagement`. Nó có thể quản lý version, scope và một số thuộc tính khác của dependency khi consumer sử dụng dependency đó.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>example-bom</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.12.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

Đây là một POM BOM **độc lập**. Nó không yêu cầu tải `commons-lang3` như dependency runtime của chính BOM và **không tự kéo JAR** này vào consumer chỉ nhờ việc được import.

### 2.2. Cú pháp import BOM ở consumer

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>example-bom</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn XML** phải nằm trong `<project>` của consumer, không phải file POM độc lập. Maven đọc BOM rồi nhập các **managed dependencies** của nó vào mô hình quản lý của consumer. `<scope>import</scope>` chỉ hợp lệ cho dependency loại POM **bên trong `dependencyManagement`**, không phải scope tùy ý cho một JAR.

Consumer vẫn cần **dependency thực sự** nếu code sử dụng thư viện:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
    </dependency>
</dependencies>
```

Version có thể bỏ trống vì đã có management. Nếu không có BOM, parent hoặc entry management nào quản lý artifact ấy, một dependency thiếu version thường bị Maven báo lỗi mô hình. **BOM không tự thêm dependency** vào `<dependencies>`; nó chỉ cung cấp thông tin quản lý khi dependency được yêu cầu.

### 2.3. Khóa trùng nhau phải được hiểu chính xác

Maven xác định một managed dependency bằng khóa có dạng:

```text
groupId : artifactId : type : classifier
```

Đối với JAR mặc định, `type` thường là `jar`, không có classifier, nên trong phần lớn ví dụ có thể nói ngắn là `groupId:artifactId`.

Hai BOM cùng quản lý `org.apache.commons:commons-lang3` với cùng type/classifier sẽ tranh chấp cùng managed entry. Ngược lại, một BOM quản lý artifact có classifier riêng thì không nên suy luận ngay rằng nó ghi đè JAR mặc định. Điều này đặc biệt quan trọng với `test-jar` và các artifact có type/classifier khác nhau.

**Version không phải thành phần của khóa nhận diện managed entry.** Chính vì khóa không phân biệt version mà hai entry có version 3.12.0 và 3.14.0 có thể tranh chấp.

## 3. Quy tắc quan trọng nhất: BOM import trước được ưu tiên

Giả sử hai BOM đều quản lý X:

```text
BOM A: X = 1.0
BOM B: X = 2.0

consumer imports:
  A, B
```

Consumer không có managed entry trực tiếp cho X. Theo Apache Maven *Introduction to the Dependency Mechanism*, **entry của BOM A được chọn**. Điều này cũng được nêu trong ví dụ chính thức: project Z import X rồi Y; cả X/Y đều quản lý artifact a; phiên bản của artifact a từ X được dùng vì X khai báo trước và Z không tự khai báo quản lý a.

Ví dụ XML:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>bom-a</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>bom-b</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Kết quả mong đợi cho X: **version 1.0**. Nếu chỉ đảo hai khối import để BOM B xuất hiện trước BOM A, kết quả mong đợi: **version 2.0**.

### 3.1. Vì sao không phải “last BOM wins”?

Không nên lấy mô hình “cấu hình ở dưới ghi đè cấu hình ở trên” của một số hệ thống khác áp dụng máy móc cho Maven BOM imports. Trong trường hợp **các BOM import cùng cấp**, managed entry trùng khóa được **ưu tiên theo import đứng trước**, miễn không có managed entry riêng của consumer hoặc quan hệ inheritance làm thay đổi model đang xét.

```text
consumer:
  import A
  import B

X:
  A = 1.0     <-- được chọn
  B = 2.0     <-- không thay version của X

consumer:
  import B
  import A

X:
  B = 2.0     <-- được chọn
  A = 1.0
```

Đây là quyết định tại **giai đoạn xây dựng effective dependencyManagement**, không phải vì thư viện 1.0 nằm trong cache trước, hoặc BOM A được Maven tải nhanh hơn.

### 3.2. BOM đứng sau vẫn đóng góp những artifact riêng

Giả sử:

```text
BOM A             BOM B
  X -> 1.0          X -> 2.0
  Y -> 5.0          Z -> 7.0
```

Consumer import A trước B. Effective management có thể có:

```text
X -> 1.0 (trùng khóa: A thắng)
Y -> 5.0 (chỉ A có)
Z -> 7.0 (chỉ B có)
```

**BOM B không bị loại bỏ toàn bộ** chỉ vì nó không thắng ở X. Entries không trùng từ BOM B vẫn có hiệu lực. Nếu consumer không thực sự phụ thuộc Z, thì dù version Z được quản lý, JAR Z không tự xuất hiện trên classpath.

Đây là hai câu hỏi riêng: **“BOM quản lý version nào?”** và **“project đang dùng artifact nào?”**

### 3.3. Import lồng nhau làm đường nguồn khó nhìn

BOM A có thể import BOM C; consumer import A trước B:

```text
consumer
├── import A
│   └── import C
│       └── managed X:1.0
└── import B
    └── managed X:2.0
```

Quá trình import là **đệ quy**. Các managed entries từ C có thể được đưa vào A rồi được consumer nhìn thấy như một phần của tập management đến từ A. Vì vậy X:1.0 có thể thắng dù bạn không tìm thấy một khai báo X trực tiếp trong phần POM hiển thị đầu tiên của A.

Khi gặp BOM chain lồng nhau, dùng `help:effective-pom` và kiểm tra POM của từng BOM, không chỉ nhìn hai khai báo import ngoài cùng.

## 4. Consumer quản lý version riêng: khác hẳn ưu tiên giữa các BOM

Consumer có thể ghi **managed dependency trực tiếp** trong chính `dependencyManagement`, cùng cấp với các import nhưng không nằm bên trong BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.13.0</version>
        </dependency>

        <dependency>
            <groupId>com.example</groupId>
            <artifactId>bom-a</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>bom-b</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Trong cấu hình này, **consumer đã tuyên bố quản lý `commons-lang3:3.13.0`**. Entry khai báo trực tiếp ở consumer được ưu tiên hơn những entry cùng khóa **chỉ đến từ import BOM**, nên version quản lý của thư viện đó không còn do thứ tự A/B quyết định.

Đây là cách override một version có chủ đích khi bạn cần khắc phục lỗi hoặc cập nhật lỗ hổng nhưng chưa thể đổi toàn bộ BOM. Tuy nhiên, override có thể làm bộ thư viện lệch khỏi tập version đã được nhà cung cấp BOM thử nghiệm; cần test lại toàn bộ chức năng liên quan.

**Nên ghi rõ vì sao override tồn tại** trong comment POM hoặc tài liệu version policy: issue, version được chấp thuận, phạm vi ứng dụng và điều kiện gỡ bỏ. Đừng ghi nhiều override tùy tiện làm mất ý nghĩa quản lý tập trung của BOM.

### 4.1. Direct dependency có version explicit là một trường hợp khác

Nếu consumer khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
```

thì version `3.14.0` là lựa chọn được ghi **trực tiếp trên dependency**. Không nên phát biểu rằng BOM import trước sẽ tự động override mọi version explicit trong `<dependencies>`.

Cách quản lý nhất quán thường là:
- một nơi quyết định version trong `dependencyManagement` của consumer/parent/BOM;
- `<dependencies>` khai báo các artifact **thực sự sử dụng**, bỏ version nếu đã có management.

Nếu thật sự cần override riêng một dependency trực tiếp, hãy làm rõ lý do và xem `dependency:tree`; đừng vô tình để hai nguồn version mâu thuẫn không được giải thích.

### 4.2. Dependency mediation không phải import order

Khi **không có dependencyManagement thích hợp**, Maven cần giải quyết xung đột version trong graph:

```text
app -> service-a -> X:1.0
app -> service-b -> X:2.0
```

Maven 3 thường dùng **nearest definition wins**: đường ngắn nhất tính từ project gốc có ưu tiên; nếu hai đường cùng độ sâu, **first declaration wins** trong thứ tự dependency của consumer.

Còn với BOM:

```text
app dependencyManagement:
    import bom-a (X:1.0)
    import bom-b (X:2.0)
```

Ưu tiên đầu tiên là **merge management**: app quản lý X:1.0 vì BOM A import trước. Sau đó, nếu X thực sự xuất hiện trong graph bắc cầu, managed version có thể được áp dụng và **có ưu tiên so với dependency mediation thông thường cho transitive dependencies**.

**Hai loại thứ tự khác nhau:**
- Thứ tự `<dependencyManagement>` **import BOM** ảnh hưởng managed entry nào được chọn.
- Thứ tự các `<dependency>` trong `<dependencies>` thường có thể làm tie-break của dependency graph khi không có management điều chỉnh.
- Thứ tự `<modules>` trong aggregator không phải quy tắc ưu tiên version BOM.

## 5. Parent POM, BOM và quy tắc quản lý nhiều tầng

### 5.1. Parent quản lý version

Parent POM có thể định nghĩa:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.12.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Module con kế thừa các managed entries theo cơ chế inheritance. Nếu child **khai báo trực tiếp** một managed entry cùng khóa với version khác, entry trực tiếp của child **có ưu tiên** so với version của parent (đây là quy tắc được giải thích trong Maven Dependency Mechanism guide).

Tuy nhiên, **đừng đồng nhất “child import BOM” với “child khai báo trực tiếp managed entry”** trong mọi tình huống. Khi parent đã quản lý artifact, việc child import thêm BOM có thể chịu ảnh hưởng của quá trình model merge. Để override chắc chắn một entry từ parent, hãy khai báo trực tiếp managed entry trong child rồi kiểm tra effective POM của child, thay vì chỉ đảo import order và suy luận.

### 5.2. BOM import qua nhiều lớp

Một BOM có thể import những BOM khác, một parent có thể quản lý phiên bản chung và consumer cũng có thể quản lý riêng. Vì vậy, một project thực tế có thể có:

```text
organization-parent
  └── product-parent
        └── app
              ├── import platform-bom
              └── import testing-bom
```

Kết quả không thể chỉ dựa vào một hàng `<version>` trong file app. Cần xét **effective model sau khi kế thừa parent**, mở các BOM lồng nhau và các profile active.

Giới hạn quan trọng: không được tạo **vòng import/parent**:

```text
parent --imports--> child-bom
child-bom --parent--> parent
```

Để dựng parent, Maven phải nhập BOM; nhưng để dựng BOM lại cần parent. Cấu hình này có thể fail ngay tại model building. Đừng cố import BOM nằm trong submodule của chính importer khi BOM chưa có sẵn để phân giải: đây là rủi ro bootstrap được tài liệu Maven cảnh báo. Nên tạo/release BOM **độc lập** trước consumer.

### 5.3. Plugin dependencies không bị BOM project quản lý toàn bộ

`dependencyManagement` trong POM consumer quản lý **project dependencies**, không tự điều khiển transitive dependencies của Maven plugins (Compiler, Surefire, Help Plugin...). Vì vậy thấy một plugin dùng commons-lang3 ở version khác **không chứng minh** BOM precedence của app bị sai.

Để điều tra, phân biệt rõ:
- project compile/runtime/test classpath;
- dependencies của plugin được Maven dùng để thực thi build;
- local repository cache có thể chứa nhiều version.

## 6. Ví dụ đầy đủ: hai BOM độc lập và ứng dụng Java 17

Chúng ta sẽ tạo hai BOM tự quản lý version cùng một consumer. Có **ba POM hoàn chỉnh** và **một class Java hoàn chỉnh**. Không cần database, Docker hay framework đặc biệt; Maven chỉ cần có quyền tải các plugin và thư viện công khai khi local cache chưa có.

Tập version được dùng để quan sát ưu tiên:

| Artifact | BOM thứ nhất | BOM thứ hai | Kết quả dự kiến nếu import thứ nhất trước |
| --- | --- | --- | --- |
| `org.apache.commons:commons-lang3` | 3.12.0 | 3.14.0 | **3.12.0** |
| `commons-io:commons-io` | 2.16.1 | Không quản lý | **2.16.1** |
| `com.google.code.gson:gson` | Không quản lý | 2.11.0 | **2.11.0** |

Ứng dụng cố ý sử dụng cả ba thư viện để có thể xem phiên bản trong resolved dependency graph.

### 6.1. Cấu trúc

```text
bom-order-lab/
├── bom-first/
│   └── pom.xml
├── bom-second/
│   └── pom.xml
└── consumer/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── com/example/bomorder/App.java
```

Mở terminal ở `bom-order-lab`. Không tạo một aggregator root POM vừa import hai BOM chưa tồn tại vừa yêu cầu build chúng trong cùng model. Trong ví dụ này, hai BOM độc lập được `install` **trước consumer**, để mô phỏng cách một BOM đã phát hành vào repository được dự án khác sử dụng.

### 6.2. Tệp `bom-first/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.bomorder</groupId>
    <artifactId>bom-first</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.12.0</version>
            </dependency>
            <dependency>
                <groupId>commons-io</groupId>
                <artifactId>commons-io</artifactId>
                <version>2.16.1</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

`bom-first` quản lý Commons Lang và Commons IO. Nó không có parent trỏ về consumer, không import `bom-second` và không cần compile Java.

### 6.3. Tệp `bom-second/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.bomorder</groupId>
    <artifactId>bom-second</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.apache.commons</groupId>
                <artifactId>commons-lang3</artifactId>
                <version>3.14.0</version>
            </dependency>
            <dependency>
                <groupId>com.google.code.gson</groupId>
                <artifactId>gson</artifactId>
                <version>2.11.0</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

`bom-second` quản lý Commons Lang khác version với BOM đầu, đồng thời có entry Gson chỉ nó cung cấp. Vì vậy Gson là phép thử chứng minh BOM đứng sau vẫn có tác dụng.

### 6.4. Tệp `consumer/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.bomorder</groupId>
    <artifactId>consumer</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.bomorder</groupId>
                <artifactId>bom-first</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
            <dependency>
                <groupId>com.example.bomorder</groupId>
                <artifactId>bom-second</artifactId>
                <version>1.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
        </dependency>
        <dependency>
            <groupId>commons-io</groupId>
            <artifactId>commons-io</artifactId>
        </dependency>
        <dependency>
            <groupId>com.google.code.gson</groupId>
            <artifactId>gson</artifactId>
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
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
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

Đọc POM theo hai phần:
- `dependencyManagement` **chỉ import BOM**; thứ tự là `bom-first`, rồi `bom-second`.
- `dependencies` **khai báo ba JAR thực sự dùng**, bỏ version để nhận từ managed entries.

### 6.5. Tệp `consumer/src/main/java/com/example/bomorder/App.java`

```java
package com.example.bomorder;

import com.google.gson.Gson;
import org.apache.commons.io.FilenameUtils;
import org.apache.commons.lang3.StringUtils;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("lang3=" + StringUtils.upperCase("maven"));
        System.out.println("io=" + FilenameUtils.getExtension("notes.txt"));
        System.out.println("gson=" + new Gson().toJson("ready"));
    }
}
```

Class trên chạy được với Java 17. Nó sử dụng một API ổn định của Commons Lang, Commons IO và Gson để minh họa classpath. `StringUtils.upperCase("maven")` trả về `MAVEN`, `FilenameUtils.getExtension("notes.txt")` trả `txt`, và Gson xuất JSON string có dấu ngoặc kép.

### 6.6. Cài hai BOM rồi build consumer

Từ thư mục `bom-order-lab`:

```bash
mvn -version
mvn -f bom-first/pom.xml install
mvn -f bom-second/pom.xml install
mvn -f consumer/pom.xml clean verify
```

Hai lệnh đầu cài BOM dạng POM vào local repository. Đặc biệt, **thứ tự `install` hai BOM không quyết định version thắng**. Consumer đọc **thứ tự import trong chính POM của nó**, dù bạn đã cài BOM thứ hai trước hoặc sau trên máy.

Lệnh cuối biên dịch project Java 17, chạy các phase đến `verify`. Log Maven tùy JDK, cấu hình repository và cache; có thể cần kết nối internet để tải plugin và ba thư viện lần đầu.

### 6.7. Quan sát effective dependencyManagement

Chạy:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
```

Trong cấu hình hiệu lực, những managed versions quan trọng sẽ tương ứng:

```text
org.apache.commons:commons-lang3  -> 3.12.0
commons-io:commons-io             -> 2.16.1
com.google.code.gson:gson         -> 2.11.0
```

Đây là **bản rút gọn diễn giải** các managed entries, không phải nguyên văn XML log. Effective POM có thể chứa nhiều plugin/default entries khác. Nếu cần xem nguồn của dòng XML trong effective POM, Maven Help Plugin hỗ trợ:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true
```

`-Dverbose=true` có thể thêm các comment về nguồn khai báo. Khi POM có parent, profiles và BOM lồng nhau, chức năng này giúp xác định phần cấu hình đến từ file nào.

### 6.8. Xem artifact version trên dependency graph

Chạy:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
```

Các dòng quan trọng **dự kiến** (đã bỏ cấu trúc nhánh/log phụ):

```text
org.apache.commons:commons-lang3:jar:3.12.0:compile
commons-io:commons-io:jar:2.16.1:compile
com.google.code.gson:gson:jar:2.11.0:compile
```

Maven có thể hiển thị thêm các transitive dependencies tùy POM/version; đừng coi bảng trên là toàn bộ output. **Điểm phải kiểm tra là version được chọn ở project consumer.**

Có thể lọc output:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
```

Cờ `-Dincludes` của **dependency:tree** chỉ lọc những dòng được hiển thị; nó **không thay version**, không tạo exclusion trong POM và không làm BOM khác thắng.

### 6.9. Chạy Java với dependencies thực sự được giải quyết

```bash
mvn -f consumer/pom.xml org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=com.example.bomorder.App
```

Chương trình Java in **chính xác ba dòng**:

```text
lang3=MAVEN
io=txt
gson="ready"
```

Lệnh Maven có thể in log plugin và trạng thái build trước/sau những dòng này. Đây là **stdout từ code Java**, không phải toàn bộ stdout của Maven process.

**Quan trọng:** ba dòng trên không xác minh `commons-lang3` có version 3.12.0 hay 3.14.0, vì cả hai version đều có `StringUtils.upperCase`. Phải xem `effective-pom` và `dependency:tree` để chứng minh version được quản lý và đã được chọn.

## 7. Ba thí nghiệm thay đổi ưu tiên

### Thí nghiệm A — đảo thứ tự hai BOM

Giữ `<dependencies>` của consumer y nguyên. **Chỉ hoán đổi hai khối import** bên trong `dependencyManagement` để `bom-second` đứng trước `bom-first`.

Trước:

```text
import bom-first:  commons-lang3=3.12.0
import bom-second: commons-lang3=3.14.0
=> version được quản lý 3.12.0
```

Sau:

```text
import bom-second: commons-lang3=3.14.0
import bom-first:  commons-lang3=3.12.0
=> version được quản lý 3.14.0
```

Chạy:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
mvn -f consumer/pom.xml clean verify
```

Kết quả mong đợi: `commons-lang3:3.14.0`. Gson và Commons IO giữ nguyên version vì chỉ được quản lý ở một BOM tương ứng. Code Java vẫn chạy và có thể in cùng stdout vì các method sử dụng tương thích.

**Đây là chứng cứ rằng BOM import order có ý nghĩa**, kể cả khi không thay code hoặc `<dependencies>` trực tiếp.

Khôi phục `bom-first` đứng trước `bom-second` trước thí nghiệm B.

### Thí nghiệm B — consumer override version bằng managed entry riêng

Giữ BOM order ban đầu. Trong `consumer/pom.xml`, thêm **đoạn dependency sau ở đầu `dependencyManagement/dependencies`**, ngay trước hai block import:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.13.0</version>
</dependency>
```

Đây là **đoạn XML cần chèn**, không phải POM đầy đủ. Nó phải nằm trong `dependencyManagement`, không phải trong `<dependencies>` của consumer.

Chạy lại:

```bash
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn -f consumer/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
mvn -f consumer/pom.xml clean verify
```

Version mong đợi: **commons-lang3:3.13.0**. Consumer đã quản lý trực tiếp nên không cần nhờ BOM đầu hay BOM sau quyết định. Đây là cách override version riêng có kiểm soát, **không phải khuyến nghị rằng 3.13.0 tốt nhất cho production**.

Xóa entry thử nghiệm khi xong.

### Thí nghiệm C — version explicit trên dependency trực tiếp

Trong danh sách `<dependencies>` thông thường, thay:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
</dependency>
```

bằng:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.14.0</version>
</dependency>
```

Dùng `dependency:tree` để thấy version direct explicit này. Điều đó khác với `dependencyManagement`: trường hợp này **chính dependency thực sự khai báo version**, thay vì chỉ có bản đồ quản lý version.

Sau khi quan sát, bỏ version explicit để khôi phục POM tiêu chuẩn của bài.

| Kịch bản | Thứ tự import | Managed entry riêng | Kết quả commons-lang3 |
| --- | --- | --- | --- |
| Gốc | first → second | Không | **3.12.0** |
| A — đảo import | second → first | Không | **3.14.0** |
| B — override | first → second | **3.13.0** | **3.13.0** |
| C — direct version | first → second | Không | **3.14.0** |

Bảng trên áp dụng **đúng cho các POM và thay đổi được mô tả**. Trong dự án thật có parent, profiles, BOM lồng nhau hoặc classifier đặc biệt, phải kiểm chứng thêm effective model.

## 8. Các tình huống thường gặp trong dự án thật

### 8.1. BOM trùng version của một thư viện lõi

Một project nhập BOM nền tảng và BOM của framework; cả hai quản lý phiên bản của cùng logging, JSON, HTTP hoặc utility library. Nếu import BOM công ty **trước** framework BOM, managed version của BOM công ty có thể thắng ở các key trùng, nhưng điều đó **không đảm bảo tương thích với framework**.

Trước khi thay BOM order, xem documentation/release train của các nhà cung cấp, xác định những artifact trùng nhau, chạy integration tests và ghi lại quyết định. Có trường hợp tốt hơn là dùng một **platform BOM** đã được kiểm thử tổng thể thay vì tự tổ hợp nhiều BOM không tương thích.

### 8.2. Entry riêng ở consumer so với BOM từ parent

Nếu parent quản lý artifact X, còn child import một BOM cũng quản lý X, không nên đoán “BOM child chắc chắn override parent”. Kết quả phụ thuộc mô hình đã merge. Nếu child cần X version riêng, hãy khai báo **managed entry trực tiếp trong child** rồi xác minh bằng Help Plugin. Tránh dùng thứ tự trong file con để suy ra một thuật toán merge không được kiểm chứng.

### 8.3. BOM B nằm sau nhưng thư viện của B không xuất hiện

Không hẳn là lỗi ưu tiên: một BOM chỉ thêm **version management**, không tự thêm thư viện. Nếu consumer không khai báo dependency đó và không có đường transitive nào cần tới nó, `dependency:tree` không in artifact chỉ vì BOM đã import. Dùng `help:effective-pom` để nhìn phần management.

### 8.4. Project dependency khác với plugin dependency

Một Maven plugin có classpath riêng. Việc consumer quản lý commons-lang3 version X **không tự ép** Maven Compiler Plugin hay Surefire chạy với commons-lang3 version X trong chính plugin. Nếu bạn đang nhìn output của một plugin khác, phải phân biệt **plugin dependency graph** với dependency graph của ứng dụng.

### 8.5. BOM import không phân giải được

`Non-resolvable import POM` có thể đến từ tọa độ sai, repository/mirror/proxy, credential, hoặc BOM chưa được phát hành/cài. Nếu BOM được khai báo như submodule của importer nhưng chưa có sẵn khi Maven phải dựng model, lỗi bootstrap có thể xảy ra. Nếu parent import BOM mà BOM kế thừa chính parent, đó là **vòng parent/BOM** cần sửa kiến trúc chứ không phải đổi thứ tự.

### 8.6. Có nhiều type/classifier

Khi two BOM entries trùng `groupId:artifactId` nhưng khác type/classifier, điều quan trọng là so đúng **khóa management đầy đủ**. Đừng kết luận mọi entry cùng artifactId phải tuân theo cùng một quy tắc conflict nếu chúng quản lý các biến thể artifact khác nhau. Đọc effective POM và resolved tree ở đúng module/variant.

### 8.7. Thay BOM order nhưng runtime bị lỗi

Maven chọn version theo quy tắc phân giải không có nghĩa binary API tương thích. Thay một JAR có thể gây `NoSuchMethodError`, `NoClassDefFoundError`, lỗi serialization hoặc thay đổi hành vi. Mọi lần nâng/đổi BOM order đều cần chạy unit và integration tests, kiểm tra dependency tree, artifact cuối và changelog/security advisories của thư viện.

## 9. Cách chẩn đoán nhất quán

Khi thấy version khác kỳ vọng:

1. Chạy `mvn -version` và xác định Maven project/module đang build.
2. Đọc `<dependencyManagement>` của **consumer effective POM**; liệt kê các import theo đúng thứ tự.
3. Mở POM nguồn của BOM và các BOM lồng nhau, xác định managed keys trùng và không trùng.
4. Tìm managed entry trực tiếp trong consumer, rồi xét parent và active profiles.
5. Kiểm tra direct dependency có version explicit không.
6. Chạy `help:effective-pom` để xác định model cuối.
7. Chạy `dependency:tree` để xác định version **thực sự được phân giải**.
8. Kiểm tra scope, optional, exclusions và type/classifier khi artifact thiếu hoặc version lệch.
9. Nếu build thất bại trước khi tạo model, kiểm tra BOM resolution, parent/import cycles và repository.
10. Sau khi sửa, chạy `mvn clean verify` cùng test chức năng đại diện; ghi rõ lý do thay đổi BOM order/version.

Các lệnh thường dùng:

```bash
mvn -version
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
mvn org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dincludes=org.apache.commons:commons-lang3
mvn -e clean verify
```

**Không dùng `mvn -U` như một cách “chọn BOM mới hơn”.** `-U` có vai trò kiểm tra metadata/SNAPSHOT và release chưa phân giải được theo quy tắc của Maven; nó không đảo BOM import order hoặc tự thay đổi version đã được quản lý trong POM.

Không cần xóa cả local repository chỉ vì tree dùng bản không mong muốn. Nếu effective POM chọn version X, việc xóa cache có thể chỉ khiến Maven tải lại chính X.

## 10. Bài tập tự đánh giá

**Bài 1 — hai BOM trùng entry.** BOM A quản lý X:1.0 và Y:5.0, BOM B quản lý X:2.0 và Z:7.0. Consumer import A trước B rồi khai báo dependencies X/Y/Z không có version. Kết quả: **X:1.0, Y:5.0, Z:7.0**.

**Bài 2 — đảo thứ tự.** Consumer import B trước A, các điều kiện khác giữ nguyên. X: **2.0**; Y và Z vẫn từ BOM tương ứng.

**Bài 3 — consumer ghi managed version.** Consumer import A trước B nhưng trực tiếp quản lý X:3.0 trong chính dependencyManagement. Version quản lý X: **3.0**, không do BOM đầu tiên quyết định.

**Bài 4 — BOM không thêm JAR.** Consumer import BOM có Gson 2.11.0 nhưng không khai báo Gson và không có dependency nào cần Gson. Gson có tự vào classpath không? **Không**.

**Bài 5 — parent.** Parent explicit managed X:1.0, child explicit managed X:2.0. Khi build child, entry child thông thường được ưu tiên. Vì sao vẫn cần effective POM? Vì parent/BOM/profile và các entry lồng nhau có thể làm cấu hình thực tế phức tạp.

**Bài 6 — direct version.** Consumer khai báo direct dependency X:2.0 với version explicit; hai BOM quản lý X ở 1.0 và 3.0. Đừng mặc định BOM đầu sẽ ghi đè direct explicit version; kiểm chứng resolved tree.

**Bài 7 — công cụ.** Tại sao `dependency:tree` không in thư viện chỉ có trong BOM mà project không dùng? Vì `dependencyManagement` chỉ quản lý, không tạo dependency.

**Bài 8 — policy.** Nếu đảo BOM để nâng một thư viện vì vấn đề bảo mật, cần làm gì ngoài xem tree? Kiểm tra changelog, API compatibility, unit/integration tests, artifact đóng gói và policy vulnerability.

## 11. Checklist review thay đổi BOM

- [ ] Đã ghi lại những BOM import, tọa độ và thứ tự trong consumer.
- [ ] Đã biết artifact nào trùng khóa quản lý ở các BOM.
- [ ] Đã phân biệt **BOM import trước** với **consumer managed entry trực tiếp**.
- [ ] Đã đọc effective POM cho đúng module.
- [ ] Đã đối chiếu dependency tree với version mong đợi.
- [ ] Đã kiểm tra direct explicit versions, parent và profiles.
- [ ] Đã chắc chắn BOM có thể phân giải độc lập, không vòng parent/import.
- [ ] Đã chạy kiểm thử phù hợp sau thay đổi; không chỉ nhìn BUILD SUCCESS.
- [ ] Đã ghi chú override version và chính sách cập nhật bảo mật.

**Ghi nhớ:** Khi **nhiều BOM import cùng cấp** quản lý **cùng khóa dependency**, nếu consumer **không quản lý trực tiếp entry ấy**, thì **BOM import trước có ưu tiên**. Các managed entries không trùng vẫn được giữ; consumer có thể ghi đè bằng một managed entry trực tiếp. Hãy xác nhận bằng **effective POM** (quy tắc quản lý) và **dependency:tree** (artifact/version đã được chọn).

### Tài liệu chính thức

- [Apache Maven — Introduction to the Dependency Mechanism: Importing Dependencies và BOM](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference: dependencyManagement](https://maven.apache.org/pom.html)
- [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Guide — Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Maven Resolver — How Resolver Works](https://maven.apache.org/resolver/how-resolver-works.html)
