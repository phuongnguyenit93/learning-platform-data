# Đọc nhánh bị loại do xung đột trong Maven dependency:tree

## 1. Vấn đề: cùng một thư viện xuất hiện qua nhiều đường đi

Khi ứng dụng Maven phụ thuộc hai thư viện khác nhau, cả hai có thể cùng kéo về một thư viện thứ ba nhưng ở **hai phiên bản khác nhau**. Ví dụ:

~~~text
my-app
├── first-route:1.0.0
│   └── shared-lib:1.0.0
└── second-route:1.0.0
    └── shared-lib:2.0.0
~~~

Ứng dụng không thể mặc nhiên tải cả `shared-lib:1.0.0` và `shared-lib:2.0.0` như hai bản cùng được chọn cho một dependency thông thường. Maven cần **dependency mediation** (hòa giải xung đột) để quyết định phiên bản nào tham gia dependency graph cuối cùng. Phiên bản còn lại có thể xuất hiện trong kết quả phân tích dưới dạng **omitted for conflict with ...** — nghĩa là *nhánh khai báo phiên bản đó đã bị loại khỏi graph được chọn vì xung đột*.

Điểm dễ nhầm: **omitted không có nghĩa Maven xóa khai báo dependency khỏi POM**, và cũng không tự kết luận dependency đó lỗi, mất trên repository hay có lỗ hổng bảo mật. Nó nói về quyết định **chọn một dependency node** khi Maven dựng graph.

Bài này tập trung vào cách **đọc nhánh bị loại trong `dependency:tree`**, tìm đường đã kéo phiên bản không được chọn về, hiểu vì sao Maven giữ phiên bản thắng, và dùng biện pháp quản lý version có kiểm soát.

Sau bài học, bạn sẽ:

1. Phân biệt cây phụ thuộc khai báo với graph đã được Maven hòa giải.
2. Đọc đúng cấu trúc và tọa độ trong kết quả `dependency:tree`.
3. Giải nghĩa `omitted for conflict with ...`, `omitted for duplicate` và các trạng thái bị loại khác.
4. Áp dụng quy tắc **nearest definition wins**, nếu độ sâu bằng nhau thì **first declaration wins**.
5. Tìm ra **nhánh gây xung đột**, **version được chọn** và **đường đi chính xác** của nó.
6. Dùng `-Dverbose=true` với phiên bản Maven Dependency Plugin hỗ trợ, cùng `-Dincludes`/`outputFile` để điều tra.
7. Chạy một ví dụ Java 17 có hai nhánh mang hai version của cùng library và quan sát thay đổi runtime khi thứ tự dependency đổi.
8. Đánh giá phương án sửa qua dependency trực tiếp, `dependencyManagement`/BOM, exclusions hoặc cập nhật upstream, và xác nhận lại kết quả.

## 2. Từ GAV đến dependency graph

Mỗi dependency thường có `groupId`, `artifactId` và `version` (gọi tắt **GAV**), đồng thời có thể có `type`, `classifier`, `scope` và `optional`.

Ví dụ:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>shared-lib</artifactId>
    <version>1.0.0</version>
    <scope>compile</scope>
</dependency>
~~~

Tọa độ có thể được trình bày trong log dạng:

~~~text
dev.example:shared-lib:jar:1.0.0:compile
~~~

Trong đó:

- `dev.example`: groupId.
- `shared-lib`: artifactId.
- `jar`: type/kiểu artifact.
- `1.0.0`: version.
- `compile`: scope Maven dùng cho dependency đã được xử lý.

Không đưa `scope` vào nhãn định danh file artifact; scope chi phối classpath và cách dependency được truyền theo graph. Một artifact dùng classifier `tests` hoặc type khác có thể là **biến thể** khác của cùng group/artifact. Khi điều tra conflict, nên so **đầy đủ groupId, artifactId, type và classifier**, không chỉ so tên thư viện.

### 2.1. Dependency trực tiếp và dependency bắc cầu

**Dependency trực tiếp** được khai báo trong `<dependencies>` của POM ứng dụng. **Dependency bắc cầu** (*transitive dependency*) đến từ POM của một thư viện mà ứng dụng đã phụ thuộc.

~~~text
my-app → first-route → shared-lib 1.0.0
       ↘ second-route → shared-lib 2.0.0
~~~

Cả hai nhánh đều có lý do xuất hiện: `first-route` khai version 1.0.0 và `second-route` khai version 2.0.0. Maven phải chọn version cuối cho ứng dụng, nhưng các thư viện vẫn giữ thông tin về version chúng đã yêu cầu trong POM gốc.

### 2.2. Không nhầm “node bị loại” với “file bị thiếu”

Có ba câu hỏi khác nhau:

1. **Dependency nào đã được khai báo ở nhánh nào?** Xem POM của parent/library và verbose tree.
2. **Phiên bản nào thực tế được Maven chọn?** Xem resolved tree không verbose và classpath thực.
3. **Artifact đó có tải được từ repository không?** Xem log resolver/repository khi build; đây là vấn đề khác với omitted conflict.

Một dòng `omitted for conflict with 1.0.0` không chứng minh file `2.0.0.jar` từng được tải thành công. Maven có thể biết version từ metadata của POM để đưa ra quyết định; phân giải file vật lý là bước liên quan nhưng không đồng nhất.

## 3. Cách đọc cây dependency theo thụt đầu dòng

Ví dụ đầu ra ở dạng `text`, đã bỏ tiền tố `[INFO]` để tập trung đọc:

~~~text
dev.example:my-app:jar:1.0.0
+- dev.example:first-route:jar:1.0.0:compile
|  \- dev.example:shared-lib:jar:1.0.0:compile
\- dev.example:second-route:jar:1.0.0:compile
   \- (dev.example:shared-lib:jar:2.0.0:compile - omitted for conflict with 1.0.0)
~~~

**Đây là log minh họa** của một verbose dependency tree, không phải cam kết ký tự và thứ tự log giống tuyệt đối ở mọi bản Maven/Dependency Plugin.

Các ký hiệu:

| Dấu/ký hiệu | Ý nghĩa |
| --- | --- |
| `+-` | Một dependency con, chưa phải con cuối của node cha |
| `\-` | Dependency con cuối trong nhánh đang hiển thị |
| `|` | Đường nối cho biết vẫn còn nhánh anh em bên dưới |
| Khoảng trắng đầu dòng | **Độ sâu** của dependency so với root |
| `(... omitted for conflict with 1.0.0)` | Node được phát hiện nhưng **không được chọn** do Maven chọn version 1.0.0 |
| `:compile` | Scope sau khi Maven xử lý dependency trong graph tương ứng |

Đọc từ trên xuống:

- Root là project `my-app`.
- `first-route` nằm trực tiếp dưới `my-app`: sâu 1 cạnh.
- `shared-lib:1.0.0` nằm dưới `first-route`: sâu 2 cạnh.
- `second-route` cũng là dependency trực tiếp.
- `shared-lib:2.0.0` nằm dưới `second-route`: cũng sâu 2 cạnh, nhưng bị loại do version 1.0.0 thắng.

Dòng bị loại giữ lại **ngữ cảnh cha** giúp bạn biết *ai đã yêu cầu phiên bản bị loại*. Đây chính là giá trị của verbose tree khi cần xử lý xung đột.

**Đừng đọc một node bị loại như một phiên bản đang chạy.** Khi classpath thực chỉ có một `shared-lib` cho tọa độ loại JAR thông thường, dependency bị omitted không phải phiên bản được Maven chọn để cung cấp class cho ứng dụng.

## 4. Vì sao Maven chọn một phiên bản và bỏ phiên bản kia?

### 4.1. Nearest definition wins — nhánh gần root hơn thắng

Quy tắc cơ bản của Maven dependency mediation là chọn **định nghĩa gần dự án hiện tại hơn**.

~~~text
app
├── one
│   └── two
│       └── common:2.0.0     (sâu 3)
└── three
    └── common:1.0.0         (sâu 2)
~~~

Trong trường hợp không có cơ chế quản lý version ghi đè khác, Maven chọn `common:1.0.0` vì đường `app → three → common` ngắn hơn đường `app → one → two → common`. Version số lớn hơn **không được ưu tiên** chỉ vì nó “mới hơn”.

Đây là ý nghĩa của “nearest”: **khoảng cách trong dependency tree**, không phải khoảng thời gian phát hành, không phải vị trí file JAR trong local repo và không phải mức độ nổi tiếng của thư viện.

### 4.2. Nếu bằng độ sâu: first declaration wins

Nếu cả hai đường đi có cùng số cạnh:

~~~text
app
├── alpha
│   └── common:1.0.0         (sâu 2)
└── beta
    └── common:2.0.0         (sâu 2)
~~~

thì **dependency được khai báo trước** trong danh sách phù hợp có thể quyết định kết quả; ở ví dụ này `alpha` đứng trước `beta`, nên version 1.0.0 thắng nếu không có management hoặc yếu tố khác chi phối. Đảo thứ tự khai báo `alpha` và `beta` trong `app/pom.xml` có thể đổi version được chọn thành 2.0.0.

Đây là lý do không nên dùng thứ tự dependency làm chính sách quản lý version trong một ứng dụng lớn: nó rất dễ bị thay đổi bởi lần refactor POM.

### 4.3. Direct dependency thắng nhánh transitive do gần hơn

Nếu `app` trực tiếp khai báo:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>common</artifactId>
    <version>2.0.0</version>
</dependency>
~~~

thì đường `app → common:2.0.0` có độ sâu **1**, gần hơn các đường transitive sâu 2 hoặc 3. Đây là một cách ép version được chọn khi ứng dụng **thực sự sử dụng trực tiếp** `common`, nhưng phải đảm bảo version này tương thích với các thư viện khác.

**Không khuyến nghị** thêm dependency trực tiếp chỉ như một mẹo tạm thời khi định nghĩa version dùng chung nên nằm trong `dependencyManagement`/BOM của dự án.

### 4.4. dependencyManagement có thể ghi đè mediation cho transitive

Trong `<dependencyManagement>`, ứng dụng hoặc parent/BOM có thể quản lý version của `common`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>common</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Khi một nhánh kéo `common` như transitive dependency, Maven có thể áp phiên bản được quản lý theo quy tắc Maven model/dependency resolver. **Dependency management cho transitive dependency được ưu tiên hơn mediation thuần túy**. Nó không tự thêm `common` vào graph nếu không có nhánh nào dùng `common`.

Khi dự án import một BOM, BOM là POM chứa dependency management được dùng với `type=pom` và `scope=import` trong `<dependencyManagement>`. Version chọn cuối có thể đến từ BOM/parent thay vì version trong POM của một thư viện.

Vì vậy **đừng luôn giải thích `omitted for conflict` chỉ bằng nearest wins** trước khi kiểm tra dependencyManagement, parent và profile. Một dòng log có thể có thông tin “version managed from ...”, và thông tin đó cần được xem cùng effective POM.

## 5. Các loại “omitted” trong verbose tree

Cụm từ `omitted` nghĩa chung là node/nhánh được biết đến nhưng không nằm trong graph được chọn theo cách đó. Tuy nhiên **lý do mới quyết định hướng xử lý**.

### 5.1. omitted for conflict with ...

Ví dụ:

~~~text
(dev.example:common:jar:2.0.0:compile - omitted for conflict with 1.0.0)
~~~

Cách đọc:

1. Nhánh đang xem có khai báo `common:2.0.0`.
2. Maven chọn `common:1.0.0` cho dependency tương ứng ở graph cuối.
3. Cần tìm node `common:1.0.0` **không bị omitted** ở nhánh khác để biết ai kéo bản thắng về.
4. Kiểm tra độ sâu, thứ tự khai báo và dependencyManagement để giải thích vì sao bản đó thắng.

Cụm `omitted for conflict with 1.0.0` mô tả **kết quả lựa chọn**, không nhất thiết cho biết nguyên nhân sâu nhất nếu model có parent/BOM/version managed.

### 5.2. omitted for duplicate

Ví dụ:

~~~text
(dev.example:common:jar:1.0.0:compile - omitted for duplicate)
~~~

Đây thường có nghĩa **cùng dependency đã hiện diện ở đường khác**, Maven loại sự lặp lại trong serialized/resolved dependency tree. Nó **không phải xung đột khác version**. Không cần lập tức nâng hoặc hạ version: tìm xem artifact đã được chọn ở đâu rồi cân nhắc có cần sửa POM không.

Nếu một dependency cùng GAV xuất hiện ở nhiều nhánh, việc nó được lặp trong model gốc là bình thường đối với dependency bắc cầu. Maven không nhất thiết phải đặt cùng JAR hai lần trên classpath để phản ánh tất cả các nhánh khai báo.

### 5.3. omitted for cycle

Ví dụ minh họa:

~~~text
(... - omitted for cycle)
~~~

Một nhánh sẽ tạo **chu kỳ dependency** nếu tiếp tục đi sâu. Đây không đồng nghĩa với xung đột version; cần xem quan hệ phụ thuộc giữa các modules/artifacts và tránh cấu trúc vòng khi có thể. Không nên giải quyết cycle bằng cách chỉ đổi version ngẫu nhiên.

### 5.4. Các chú thích khác liên quan đến version/scope

Trong một số phiên bản Plugin/Maven, verbose tree còn có thể thể hiện thay đổi do version management hoặc scope selection, chẳng hạn dạng `version managed from ...` hoặc một thông báo về scope được điều chỉnh. **Đây không nhất thiết là “conflict” theo cùng nghĩa hai version cạnh tranh do nearest wins**.

Cách giải thích an toàn:

- Xác định **artifact nào** đang được nhắc đến (đủ groupId/artifactId/type/classifier).
- Xác định **version được chọn cuối**.
- Xác định **version ban đầu từ nhánh**.
- Tìm **nguồn của version được quản lý**, nếu có.
- Không chỉ grep từ `omitted` rồi kết luận lỗi dependency.

### 5.5. Omitted khác excluded và optional

Một dependency có thể **không xuất hiện trong tree ngay từ đầu** vì:

- `<exclusions>` loại nó ở một đường truyền bắc cầu.
- Dependency của thư viện được khai báo `optional=true` nên thường không tự truyền tới consumer.
- Scope trong một đường truyền khiến artifact không nằm trong classpath/scope đang quan sát.
- Profile, dependency type/classifier, repository hoặc cơ chế resolver khác làm graph khác với suy luận.

Vì vậy một node **không có trong output** không đồng nghĩa nó bị `omitted for conflict`. Cần đọc POM của nhánh gốc, filter/scope và cấu hình môi trường.

## 6. Bật verbose dependency tree đúng phiên bản plugin

### 6.1. Lệnh không verbose

Ở thư mục chứa `pom.xml` của ứng dụng:

~~~bash
mvn -B -ntp dependency:tree
~~~

Lệnh này thường hiển thị **graph dependency đã được Maven chọn**, đủ để biết version thực tế nhưng không phải lúc nào cũng giữ các nhánh không được chọn.

Để cố định bản plugin dùng khi chẩn đoán, ví dụ **Maven Dependency Plugin 3.11.0**:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Cách gọi đầy đủ tránh phụ thuộc plugin version mặc định/đã quản lý trong POM hiện tại.

### 6.2. Bật verbose để xem node bị loại

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
~~~

Theo tài liệu của goal `dependency:tree` ở Maven Dependency Plugin 3.11.0, tham số `verbose` có ý nghĩa **include omitted nodes in the serialized dependency tree**, mặc định là `false`.

**Lưu ý lịch sử quan trọng:** một số bản Maven Dependency Plugin 3.x cũ từng không hỗ trợ hoặc không hoạt động đúng với `-Dverbose`; tài liệu giải thích conflict bản 3.1.2 còn ghi chú tính năng bị bỏ khỏi chuỗi 3.0 và gợi ý dùng 2.10. Vấn đề này đã được theo dõi trong Apache issue MDEP-644, còn tài liệu tham số phiên bản 3.11.0 hiện nay liệt kê `verbose` trở lại. Vì vậy **luôn pin đúng phiên bản plugin**, kiểm tra log có các node `omitted` thật, không suy rằng thêm `-Dverbose` vào bất kỳ plugin version nào đều đủ.

Với môi trường cũ chưa nâng được plugin và verbose không hiển thị omitted nodes, có thể:

1. Dùng plugin version đã được xác nhận hỗ trợ trong môi trường đó.
2. Đọc POM của các nhánh transitive, so lại các version khai báo và cây đã được chọn.
3. Kiểm tra `dependencyManagement`/BOM và effective POM.
4. Nếu bắt buộc dùng plugin cổ điển 2.10 để quan sát, **kiểm chứng output** vì công cụ rất cũ có thể không mô tả chính xác mọi đặc điểm resolver Maven 3+.

Không nên dựa duy nhất vào một log cũ để quyết định thay version production.

### 6.3. Thu hẹp theo groupId:artifactId

Nếu tree quá dài, lọc theo artifact cần điều tra:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true -Dincludes=dev.example:shared-lib
~~~

`includes` nhận pattern cho `groupId:artifactId:type:version`; có thể bỏ các thành phần phía sau khi không cần. Filter là **lựa chọn hiển thị**, không phải `<exclusions>` làm thay đổi classpath. Với artifact `common`, dùng đúng GAV đang nghi ngờ; đừng lọc trùng tên artifactId của nhóm khác rồi nhầm.

Nếu filter làm mất thông tin cần xem, chạy **verbose tree không filter** trước và sau đó mới thu hẹp. Một số trường hợp filter có thể giữ parent path nhưng không đưa đủ các node người đọc mong đợi.

### 6.4. Ghi output ra file

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true -DoutputType=text -DoutputFile=target/dependency-tree-verbose.txt
~~~

`outputFile` ghi kết quả ra file; `outputType=text` chọn định dạng cây chữ. Thư mục `target` cần tồn tại hoặc plugin phải tạo được đường dẫn; nếu không, dùng `-DoutputFile=dependency-tree-verbose.txt` ngay tại thư mục hiện tại.

Tùy version Plugin, `outputType` còn hỗ trợ `dot`, `graphml`, `tgf` và `json` (JSON từ 3.7.0); các định dạng này hữu ích cho tự động hóa hoặc trực quan hóa. Khi mục tiêu là đọc chú thích `omitted for conflict`, **text + verbose** thường dễ hiểu nhất; không giả định mọi định dạng đều hiển thị annotation giống hệt văn bản.

### 6.5. Filter scope

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dscope=runtime
~~~

`-Dscope=runtime` là filter theo scope trong kết quả của goal, **không tự thay đổi dependency scopes trong `pom.xml`**. Khi điều tra compile/runtime conflict, nên xem cả tree tổng thể vì việc filter có thể làm mất nhánh giải thích nguyên nhân. Những khác biệt giữa `test`, `provided` và `runtime` là nguyên nhân phổ biến khiến một artifact xuất hiện ở lần chạy này nhưng không ở lần khác.

## 7. Quy trình đọc nhánh bị loại một cách có hệ thống

Mỗi lần gặp xung đột version trong một dự án, thực hiện theo thứ tự:

**Bước 1 — xác định phiên bản đang được chọn:**

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
~~~

Tìm bản `common` **không nằm trong dấu ngoặc omitted**. Ghi đủ `groupId:artifactId:type:version:scope`.

**Bước 2 — bật verbose để tìm nhánh loser:**

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
~~~

Tìm `omitted for conflict with ...` và quan sát node cha trực tiếp, ông/bà và root. Đó là **đường nguồn** của version bị loại.

**Bước 3 — vẽ hai đường đi:**

~~~text
winner: app → alpha → common:1.0.0
loser : app → beta  → common:2.0.0 (omitted)
~~~

Đếm cạnh từ `app` đến `common` ở mỗi đường; nếu bằng nhau, xem thứ tự các dependencies trong `app/pom.xml` hoặc nơi model hiệu lực định nghĩa chúng.

**Bước 4 — tìm phần quản lý version:**

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Tìm `dependencyManagement`, parent, BOM import, profile active và version của dependency quan tâm. Nếu có version managed, đừng kết luận kết quả thuần từ độ sâu.

**Bước 5 — xem classpath/runtime thực tế:** kiểm tra version selected, artifact được tải, log ứng dụng và test. `dependency:tree` mô tả dependency graph, nhưng không bảo đảm API binary compatibility. Nếu nghi ngờ lỗi như `NoSuchMethodError`, hãy tái hiện bằng integration test hoặc chạy chương trình phù hợp.

**Bước 6 — sửa ở cấp đúng:** nâng nhánh thư viện nếu được hỗ trợ, quản lý version thống nhất bằng BOM/`dependencyManagement`, khai direct dependency nếu app dùng nó trực tiếp, hoặc exclude một nhánh có lý do chính đáng. Tránh sửa chỉ để mất dòng `omitted` trong log.

**Bước 7 — xác minh lại:** chạy `dependency:tree` thường + verbose, `mvn clean verify`, test runtime. Với project nhiều module, kiểm tra **đúng module bị lỗi**; reactor modules có thể có graph/version khác nhau.

## 8. Bài thực hành Java 17 hoàn chỉnh: hai nhánh, hai version

Để không phụ thuộc vào việc một thư viện public ngẫu nhiên thay đổi graph giữa các năm, ví dụ này **tự tạo các artifact mẫu**. Có năm project Maven nhỏ:

1. `shared-v1`: artifact `dev.example:shared-lib:1.0.0`.
2. `shared-v2`: artifact `dev.example:shared-lib:2.0.0`.
3. `first-route`: phụ thuộc `shared-lib:1.0.0`.
4. `second-route`: phụ thuộc `shared-lib:2.0.0`.
5. `app`: phụ thuộc `first-route` **trước** `second-route`; hai đường cùng độ sâu.

Chạy bằng **JDK 17+ và Maven 3.9.x**; phiên bản Compiler Plugin cố định ở 3.14.0; JAR Plugin 3.4.2. Lần chạy đầu cần mạng để Maven tải plugin nếu cache chưa có. Mọi artifact demo chỉ nằm trong **local repository của máy học**, không deploy lên kho chung.

Cấu trúc:

~~~text
maven-conflict-lab/
├── shared-v1/
│   ├── pom.xml
│   └── src/main/java/dev/example/shared/SharedValue.java
├── shared-v2/
│   ├── pom.xml
│   └── src/main/java/dev/example/shared/SharedValue.java
├── first-route/
│   ├── pom.xml
│   └── src/main/java/dev/example/first/FirstRoute.java
├── second-route/
│   ├── pom.xml
│   └── src/main/java/dev/example/second/SecondRoute.java
└── app/
    ├── pom.xml
    └── src/main/java/dev/example/app/Main.java
~~~

Các project là **năm Maven project độc lập**; không dùng parent/aggregator chung để tránh hiểu nhầm reactor xử lý hai version cùng artifact như hai modules đồng cấp. Bạn sẽ `install` chúng lần lượt vào local repository.

### 8.1. Tạo shared-lib phiên bản 1.0.0

Toàn bộ `shared-v1/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>shared-lib</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`shared-v1/src/main/java/dev/example/shared/SharedValue.java`:

~~~java
package dev.example.shared;

public final class SharedValue {
    private SharedValue() {
    }

    public static String label() {
        return "library-v1";
    }
}
~~~

Tất cả version của bài lab có cùng `groupId` và `artifactId` cho thư viện dùng chung, nhưng **khác `version`**.

### 8.2. Tạo shared-lib phiên bản 2.0.0

Toàn bộ `shared-v2/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>shared-lib</artifactId>
    <version>2.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`shared-v2/src/main/java/dev/example/shared/SharedValue.java`:

~~~java
package dev.example.shared;

public final class SharedValue {
    private SharedValue() {
    }

    public static String label() {
        return "library-v2";
    }
}
~~~

**Chú ý:** hai JAR chứa class **cùng tên đầy đủ** `dev.example.shared.SharedValue` và có cùng chữ ký method `label()`. Việc class chứa hai literal khác nhau là thủ thuật an toàn để thấy chính xác runtime chọn JAR nào. Trong sản phẩm thật, các version có thể khác API và gây lỗi runtime nghiêm trọng.

### 8.3. Tạo first-route phụ thuộc v1

Toàn bộ `first-route/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>first-route</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>shared-lib</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`first-route/src/main/java/dev/example/first/FirstRoute.java`:

~~~java
package dev.example.first;

import dev.example.shared.SharedValue;

public final class FirstRoute {
    private FirstRoute() {
    }

    public static String text() {
        return "first -> " + SharedValue.label();
    }
}
~~~

### 8.4. Tạo second-route phụ thuộc v2

Toàn bộ `second-route/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>second-route</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>shared-lib</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`second-route/src/main/java/dev/example/second/SecondRoute.java`:

~~~java
package dev.example.second;

import dev.example.shared.SharedValue;

public final class SecondRoute {
    private SecondRoute() {
    }

    public static String text() {
        return "second -> " + SharedValue.label();
    }
}
~~~

### 8.5. Tạo app phụ thuộc cả hai route

Toàn bộ `app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>conflict-app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <!-- Khai báo first-route TRƯỚC second-route -->
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>first-route</artifactId>
            <version>1.0.0</version>
        </dependency>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>second-route</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`app/src/main/java/dev/example/app/Main.java`:

~~~java
package dev.example.app;

import dev.example.first.FirstRoute;
import dev.example.second.SecondRoute;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(FirstRoute.text());
        System.out.println(SecondRoute.text());
    }
}
~~~

Ứng dụng gọi cả hai route. Mỗi route đã được biên dịch với một version riêng của `shared-lib`, nhưng khi ứng dụng chạy, dependency resolver thường chỉ chọn **một version** cho classpath.

### 8.6. Build năm project đúng thứ tự

Mở terminal ở thư mục **`maven-conflict-lab`**. Chạy tuần tự:

~~~bash
java -version
mvn -version
mvn -B -ntp -f shared-v1/pom.xml clean install
mvn -B -ntp -f shared-v2/pom.xml clean install
mvn -B -ntp -f first-route/pom.xml clean install
mvn -B -ntp -f second-route/pom.xml clean install
mvn -B -ntp -f app/pom.xml clean package
~~~

Đây là chuỗi lệnh minh họa cho shell hỗ trợ Maven; Windows PowerShell cũng chấp nhận đường dẫn tương đối với `/` trong tham số `-f` thông thường.

**Vì sao build theo thứ tự đó?** Hai version `shared-lib` phải được cài vào local Maven repository trước khi các route tìm dependency của chúng. Hai route phải được cài trước khi app phân giải chúng. `mvn install` ghi artifact vào local repository hiện tại, không publish ra remote repository. Mã mẫu không có unit test, nên `mvn package` không kiểm chứng hành vi nghiệp vụ; phần chạy Java sau đây là kiểm tra chủ đích.

### 8.7. Xem tree bình thường và verbose

Tại thư mục **`maven-conflict-lab/app`**:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
~~~

Ở tree bình thường, bạn kỳ vọng thấy **`shared-lib:1.0.0`** là version được chọn. Trong verbose tree, nhánh `second-route` mang `shared-lib:2.0.0` có thể xuất hiện dạng `omitted for conflict with 1.0.0`.

Mẫu kết quả rút gọn:

~~~text
dev.example:conflict-app:jar:1.0.0
+- dev.example:first-route:jar:1.0.0:compile
|  \- dev.example:shared-lib:jar:1.0.0:compile
\- dev.example:second-route:jar:1.0.0:compile
   \- (dev.example:shared-lib:jar:2.0.0:compile - omitted for conflict with 1.0.0)
~~~

**Cơ chế:** hai version của `shared-lib` đều ở độ sâu 2 từ app. `first-route` được khai báo trước, nên bản 1.0.0 thắng theo quy tắc tiebreak của dependency mediation trong trường hợp này.

### 8.8. Chạy ứng dụng và kiểm tra stdout

Tại `app`, sau khi build thành công:

~~~bash
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=dev.example.app.Main
~~~

Các dòng **do chương trình Java in ra stdout**:

~~~text
first -> library-v1
second -> library-v1
~~~

Dù `SecondRoute` được biên dịch dựa trên `shared-lib:2.0.0`, app chọn `shared-lib:1.0.0` cho runtime classpath. Vì hai version của ví dụ có **cùng method signature**, chương trình chạy bình thường nhưng trả về string của class từ bản thắng.

**Bài học:** “compile thành công” không chứng minh các thư viện phụ thuộc đã nhận đúng **hành vi runtime** mà tác giả thư viện mong đợi.

### 8.9. Đảo thứ tự hai dependency trong app

Trong `app/pom.xml`, chuyển block dependency `second-route` **lên trước** `first-route`; giữ nguyên tất cả version.

Chạy lại:

~~~bash
mvn -B -ntp clean package
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
mvn -B -ntp org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=dev.example.app.Main
~~~

Do hai đường vẫn có cùng độ sâu nhưng `second-route` được khai báo trước, version được chọn dự kiến chuyển thành **`shared-lib:2.0.0`**. Kết quả các dòng Java in ra:

~~~text
first -> library-v2
second -> library-v2
~~~

Đây là minh họa có kiểm soát cho quy tắc “first declaration wins” khi độ sâu bằng nhau. Sau khi quan sát, **hoàn nguyên** thứ tự dependency như ban đầu trước các bài tiếp theo.

### 8.10. Cần hiểu giới hạn của ví dụ

- Demo dùng **hai JAR có class cùng tên** nhưng API tương thích để quan sát selection mà không cần framework.
- Không nên phát hành hai bản thư viện mâu thuẫn như vậy vào một ứng dụng production mà không xác nhận compatibility.
- Nếu `shared-lib:2.0.0` đã thay đổi hoặc bỏ `label()`, `SecondRoute` hoặc `FirstRoute` có thể gặp `NoSuchMethodError` hoặc lỗi linkage tùy binary được chọn.
- Runtime Java còn chịu tác động của custom classloader, application server, fat JAR, JPMS hay container; `dependency:tree` là nguồn thông tin chính về Maven graph, **không khẳng định mọi runtime classloader đều nhất thiết dùng đúng cùng thứ tự**.
- Các lệnh ở đây đã được thiết kế để người học chạy từ source; output Maven ngoài hai dòng Java phụ thuộc môi trường, version Maven và cache.

## 9. Các phương án sửa conflict có trách nhiệm

### 9.1. Nâng hoặc đồng bộ dependency upstream

Giải pháp tốt thường là nâng `first-route` và `second-route` lên các version tương thích **cùng phiên bản của shared-lib**, hoặc nâng `shared-lib` theo tài liệu compatibility của cả hai. Nếu bản upstream hiện tại đã dùng chung một version, bạn giảm nhu cầu override thủ công.

Trước khi đổi, xem changelog, binary/API compatibility, release notes và chạy test ứng dụng; không giả định bản có số version cao hơn luôn an toàn.

### 9.2. Quản lý phiên bản trung tâm bằng dependencyManagement

Nếu app cần giữ `shared-lib:2.0.0` cho mọi transitive route, có thể thêm vào **`app/pom.xml` dưới `<project>`**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>shared-lib</artifactId>
            <version>2.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Đây là **đoạn XML minh họa, không phải toàn bộ POM**. Sau khi thêm, chạy `dependency:tree` để kiểm tra version cuối được quản lý. `dependencyManagement` **không tự thêm** dependency mới; nó đặt quy tắc cho dependency khi chúng xuất hiện.

Khi project đa module dùng cùng policy, nên quản lý ở parent POM hoặc import BOM được kiểm soát, tránh mỗi module override một phiên bản mà không có tài liệu.

### 9.3. Khai trực tiếp version ứng dụng thực sự dùng

Nếu `Main` dùng class từ `shared-lib` trực tiếp, khai dependency có version được chọn trong `app/pom.xml` là hợp lý:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>shared-lib</artifactId>
    <version>2.0.0</version>
</dependency>
~~~

Dependency này ở độ sâu 1 nên có thể thắng những version ở độ sâu 2, khi không có quy tắc model khác ảnh hưởng. Nhưng điều đó **không bảo đảm** `first-route` tương thích với `shared-lib:2.0.0`. Vẫn cần test.

### 9.4. Dùng exclusions có chủ đích

Nếu nhánh `first-route` không nên kéo `shared-lib` vào consumer, có thể exclude theo **đúng đường đó**:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>first-route</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>dev.example</groupId>
            <artifactId>shared-lib</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Sau exclusion, `shared-lib:2.0.0` do `second-route` mang đến có thể trở thành version được chọn. **Exclusion áp vào một đường phụ thuộc**, không phải lệnh cấm toàn cục. Nếu `first-route` thật sự dùng API từ bản 1.0, loại nhánh có thể khiến app lỗi runtime; cần quyết định dựa trên compatibility, không dùng exclusion chỉ để “dọn đẹp” tree.

### 9.5. Đừng tự sửa nội dung trong local repository

Không sửa `.pom` hoặc xóa JAR dưới `~/.m2/repository` để “ép” version. Đây là cache/artifact storage, không phải nguồn cấu hình chuẩn. Sửa POM của app/parent/BOM hoặc nâng dependency đúng quy trình; build lại trên runner sạch để xác nhận tái lập.

## 10. Khác biệt giữa conflict, version management và classpath

| Hiện tượng | Kết luận có thể rút ra | Cần xác nhận thêm |
| --- | --- | --- |
| `omitted for conflict with 1.0.0` | Nhánh kia yêu cầu version khác, graph cuối chọn 1.0.0 | Quy tắc nearest/tie hay dependencyManagement là nguyên nhân |
| `omitted for duplicate` | Một dependency trùng đã xuất hiện trong graph | Vị trí bản được chọn, không mặc nhiên là lỗi |
| `version managed from 2.0.0` | Version đã bị ảnh hưởng bởi management | Parent/BOM/định nghĩa quản lý nào áp version |
| Node không xuất hiện | Có thể do filter, scope, optional, exclusion, không kích hoạt profile hoặc resolution | Bỏ filter, xem POM và graph đúng scope |
| `NoSuchMethodError` | Có thể có binary API incompatibility tại runtime | Version JAR được load, stack trace, classloader và test |
| `ClassNotFoundException` | Có class thiếu khỏi classpath/runtime hoặc cách load sai | Packaging, scope, actual runtime classpath |
| Build xanh nhưng version sai mong đợi | Chỉ chứng minh pipeline hiện tại thành công | Test hành vi/API, dependency locks/policy |
| Dependency plugin hiển thị khác hai máy | Maven/Plugin/core, parent/BOM, profile và repo khác | Pin version, đối chiếu `mvn -version` và effective POM |

**Không coi `scope=test` là một conflict version.** Nếu một thư viện chỉ xuất hiện trong test classpath và vắng mặt ở runtime, trước hết xem scope propagation và filter; không nên kết luận nó bị omitted version conflict.

**Không coi plugin dependency graph là project dependency graph.** Dependencies của `maven-compiler-plugin` hoặc `maven-surefire-plugin` nằm trong graph plugin khác với `<dependencies>` của ứng dụng. `dependencyManagement` trong project không điều khiển transitive dependencies của Maven plugins theo cùng cơ chế; cần xử lý hai lớp riêng.

## 11. Đọc lỗi thực tế từ log và đối chiếu từng nguồn

### 11.1. Không thấy dòng omitted

Kiểm tra:

1. Bạn đã dùng `-Dverbose=true` chưa?
2. Maven Dependency Plugin đang chạy version nào? Dùng full tọa độ để pin 3.11.0.
3. Có conflict thật không hay chỉ thấy một version?
4. Có `-Dincludes`, `-Dexcludes` hoặc `-Dscope` đang ẩn nhánh?
5. Có exclusions/optional khiến dependency không được thu thập?
6. Đang chạy tree ở đúng project/module chưa?

Chỉ bật verbose không tạo conflict mới. Nếu đồ thị chỉ có một version, không có lý do để xuất `omitted for conflict`.

### 11.2. Chỉ thấy node loser mà không biết winner ở đâu

Bỏ `-Dincludes`, chạy lại verbose tree **đầy đủ**, tìm cùng `groupId:artifactId` không bị omitted. Đếm đường đi đến root, kiểm tra `dependencyManagement` bằng effective POM. Một người chỉ chụp một dòng grep `omitted` sẽ đánh mất ngữ cảnh quan trọng.

### 11.3. Vì sao version mới hơn lại bị loại?

Maven mặc định không chọn “highest version wins”. Nó thường dùng **nearest definition**, rồi **first declaration** nếu bằng depth, trừ khi version management hoặc chính sách resolver khác can thiệp. Nâng version nên là quyết định có kiểm chứng, không phải hậu quả tự động của việc thư viện mới có số lớn hơn.

### 11.4. Dùng dependencyManagement nhưng tree vẫn khác mong đợi

Kiểm tra `groupId`, `artifactId`, `type`, `classifier` đầy đủ. Mục quản lý dependency trong POM dùng khóa gồm các thành phần đó; nếu artifact biến thể là `test-jar` hoặc có classifier, một mục chỉ quản lý JAR thường có thể không khớp.

Kiểm tra `parent`, profile active, BOM import và version của POM đang chạy. Nếu app có direct dependency với version riêng, đừng giả định management overrides mọi direct version; kiểm tra model/resolution thực tế.

### 11.5. Máy cá nhân có lỗi nhưng CI không có

Dùng cùng Maven Wrapper, cùng Java, profile, settings và dependency repository. So output của:

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pom.xml
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree -Dverbose=true
~~~

Không mặc định local cache khác nhau là nguyên nhân. Nếu dependency version dùng `SNAPSHOT`, range hoặc động, metadata repository có thể thay đổi theo thời gian; cần policy khóa phiên bản phù hợp để build tái lập.

### 11.6. Muốn kiểm tra classpath cuối

Maven Dependency Plugin có goal `build-classpath` và `resolve` giúp liệt kê artifacts được phân giải:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:resolve
mvn -B -ntp org.apache.maven.plugins:maven-dependency-plugin:3.11.0:build-classpath
~~~

Kết quả classpath còn tùy hệ điều hành, scope và cấu hình plugin. Kết hợp `dependency:tree` với chạy Java/integration test để kết luận hành vi chứ không nhìn mỗi một đường trong tree.

## 12. Bài tập tự đánh giá và đáp án

**Bài A — đếm độ sâu.**

~~~text
app
├── A
│   └── B
│       └── cache:3.0.0
└── C
    └── cache:2.0.0
~~~

Không có management, `cache:2.0.0` hay `3.0.0` thắng? **Đáp án:** `2.0.0` vì gần app hơn (sâu 2 so với sâu 3). Version lớn hơn không quyết định.

**Bài B — bằng depth.**

~~~text
app
├── alpha
│   └── json:1.0.0
└── beta
    └── json:2.0.0
~~~

Nếu `alpha` và `beta` là dependencies trực tiếp cùng depth và `alpha` đứng trước, bản nào được chọn? **Đáp án:** `json:1.0.0` theo first declaration trong trường hợp không có management hay yếu tố khác. Đảo thứ tự có thể đổi winner.

**Bài C — đọc dòng omitted.**

~~~text
(app:shared-lib:jar:2.0.0:compile - omitted for conflict with 1.0.0)
~~~

Dòng trên chứng minh điều gì? **Đáp án:** nhánh được biểu diễn đã đưa `2.0.0` vào tranh chấp nhưng graph chọn `1.0.0`. Nó **không tự chứng minh** nguyên nhân là gần hơn, vì còn phải kiểm tra management/tie.

**Bài D — duplicate.** Nếu dòng ghi `omitted for duplicate`, có nhất thiết thêm một exclusion không? **Không.** Trước hết kiểm tra node đã có ở nhánh nào và classpath có xung đột thật hay không.

**Bài E — dependencyManagement.** App quản lý `shared-lib:2.0.0` nhưng POM không khai báo direct dependency. `shared-lib` có tự xuất hiện trên classpath không? **Không.** Management đặt version cho các dependencies khi chúng được đưa vào graph qua nhánh phù hợp.

**Bài F — test hành vi.** Thực hiện bài lab mục 8: (a) first-route trước, (b) second-route trước. Dự đoán 2 dòng stdout. **Đáp án:** khi first-route trước, cả hai line dùng `library-v1`; khi second-route trước, cả hai dùng `library-v2` trong classpath mô hình demo.

**Bài G — chọn cách sửa.** Nếu chỉ `second-route` còn hỗ trợ API của shared-lib 2.0, có nên ép toàn ứng dụng dùng version 2.0 ngay không? **Chưa.** Cần xác nhận `first-route` tương thích hoặc cập nhật nó. Chọn một version giải quyết graph không tự giải quyết lỗi binary/API compatibility.

**Bài H — tìm nhánh.** Một log cho `omitted for conflict with 2.9` nhưng `-Dincludes` chỉ để lại node đó. Cần làm gì? **Đáp án:** bỏ filter, xem toàn verbose tree; tìm node version 2.9 không omitted, truy từ root đến nó, rồi kiểm tra management.

## 13. Checklist khi xử lý nhánh bị loại

- [ ] Đang chạy `dependency:tree` ở đúng module và đúng Maven/Plugin version.
- [ ] Đã biết version **được chọn** trong tree thường.
- [ ] Đã bật `-Dverbose=true` trên plugin version hỗ trợ để xem omitted nodes.
- [ ] Đã phân biệt conflict, duplicate, cycle với dependency không xuất hiện do filter/exclusion/optional.
- [ ] Đã ghi đủ groupId, artifactId, type, classifier, version và scope.
- [ ] Đã tìm được cả đường đi từ root đến winner và loser.
- [ ] Đã đếm độ sâu, xem thứ tự khai báo khi bằng depth.
- [ ] Đã kiểm tra `dependencyManagement`, BOM, parent và profile nếu có version override.
- [ ] Đã xem output không filter ít nhất một lần trước khi quyết định.
- [ ] Không ép highest version nếu chưa xác nhận API/binary compatibility.
- [ ] Không dùng exclusion chỉ để biến tree thành “đẹp” nếu nhánh còn cần thư viện đó.
- [ ] Sau khi sửa đã chạy lại `dependency:tree`, `mvn clean verify` và bài test runtime cần thiết.
- [ ] Nếu là sự cố CI, đã so sánh Maven Wrapper, plugin version, effective POM và repository resolution.
- [ ] Đã lưu ngắn gọn trong PR: loser path, selected version, nguyên nhân, cách sửa và bằng chứng kiểm chứng.

## 14. Tài liệu Apache Maven chính thức

1. [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — transitive dependencies, nearest definition, first declaration khi bằng depth, dependencyManagement/BOM, scopes, exclusions và optional.
2. [Maven Dependency Plugin — dependency:tree (3.11.0)](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) — lệnh `tree`, `verbose`, `includes`, `scope`, `outputFile` và các output types.
3. [Dependency Plugin — Resolving conflicts using the dependency tree (tài liệu lịch sử)](https://maven.apache.org/plugins-archives/maven-dependency-plugin-3.1.2/examples/resolving-conflicts-using-the-dependency-tree.html) — ví dụ omitted for conflict và cảnh báo các bản 3.x cũ về verbose.
4. [Maven Dependency Plugin — Usage](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html) — mục đích dependency:tree, dependency:resolve và các goal khác.
5. [Maven Dependency Plugin — Tree Output Formats](https://maven.apache.org/plugins/maven-dependency-plugin/examples/tree-mojo.html) — xuất tree thành text/JSON/DOT/GraphML/TGF.
6. [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — dependencies, dependencyManagement, import BOM, type/classifier và các khai báo cấu hình.
7. [Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html) — điều tra POM sau khi ghép parent/profile/management.
