# Quy tắc so sánh phiên bản Maven và giới hạn của giả định SemVer

## 1. Mục tiêu: hiểu chính xác “phiên bản nào cao hơn” trong Maven

Trong Maven, một **version** là một phần của tọa độ artifact **groupId:artifactId:version**. Ví dụ **org.example:billing-api:2.4.1** chỉ một phiên bản cụ thể của thư viện. Maven cần so sánh version để xử lý các **version ranges**, lựa chọn ứng viên từ repository và một số công cụ quản lý phiên bản.

Sai lầm thường gặp là nhìn thấy các số dạng **1.2.3** rồi mặc định Maven tuân thủ đầy đủ **Semantic Versioning (SemVer) 2.0.0**. Thực tế **Maven có quy tắc so sánh phiên bản riêng**. Nó hỗ trợ nhiều định dạng không phải SemVer, chuẩn hóa một số chuỗi trông khác nhau thành cùng thứ tự so sánh, có **qualifier order** đặc biệt, coi ký tự hoa/thường như nhau trong so sánh, và **không có quy tắc bỏ qua build metadata sau dấu cộng (+) của SemVer 2.0**.

Bài này giúp trả lời:

1. Maven so sánh các thành phần số và qualifier như **alpha**, **beta**, **rc**, **SNAPSHOT**, **sp** theo thứ tự nào?
2. Vì sao **1.0** và **1.0.0** có thể bằng nhau về thứ tự so sánh?
3. Vì sao qualifier tùy ý như **foo** không thể được hiểu đơn giản là prerelease theo SemVer?
4. Vì sao range **[1.0,2.0)** có thể nhận cả **2.0-rc1**?
5. Khi nhiều dependency cùng xuất hiện, tại sao Maven **không luôn chọn version cao nhất**?
6. Làm sao tự kiểm tra kết quả thật bằng Java 17 và thư viện **maven-artifact** thay vì chỉ dựa vào cảm giác?

Đây là kiến thức về **version comparison và resolution**. Nó không phải quy tắc tự động đảm bảo tương thích API; một version tăng major/minor/patch chỉ có ý nghĩa semantic nếu *nhà phát hành thực sự tuân thủ* hợp đồng SemVer.

## 2. Phân biệt năm loại “version” trong một lệnh build

Một POM có thể chứa nhiều số phiên bản với ý nghĩa độc lập:

| Loại | Ví dụ | Vai trò |
| --- | --- | --- |
| Phiên bản artifact chính | **com.example:service:1.4.0** | Định danh đầu ra của project |
| Phiên bản dependency | **org.junit.jupiter:junit-jupiter:5.11.4** | Chọn thư viện dùng trong compile/test/runtime |
| Phiên bản Maven Core | **Apache Maven 3.9.9** | Phiên bản công cụ chạy build |
| Phiên bản plugin | **maven-compiler-plugin:3.13.0** | Chọn phiên bản goal thực hiện công việc |
| Phiên bản Java | **Java 17**, compiler release **17** | Công cụ/ngôn ngữ/API/bytecode mục tiêu |

Những version này không cùng một trục. Ví dụ **project.version=1.4.0** không đòi Maven Core phải là 1.4.0; **maven.compiler.release=17** không phải một thư viện version 17.

Khi nói “Maven chọn phiên bản mới nhất”, phải hỏi: **cho artifact nào, trong danh sách ứng viên nào, với hard constraints nào, thông qua resolver/plugin nào?** Version comparator là một công cụ để xếp thứ tự, không phải toàn bộ thuật toán dependency mediation.

## 3. SemVer 2.0.0 thực sự quy định điều gì?

SemVer 2.0 mô tả dạng:

~~~text
MAJOR.MINOR.PATCH[-PRERELEASE][+BUILDMETADATA]
~~~

Ý nghĩa thường dùng:

- **MAJOR**: thay đổi API không tương thích ngược.
- **MINOR**: thêm chức năng tương thích ngược.
- **PATCH**: sửa lỗi tương thích ngược.
- **PRERELEASE**: các định danh phân tách bằng dấu chấm sau dấu **-**, thường dùng cho alpha/beta/rc.
- **BUILD METADATA**: nằm sau **+** và **không tham gia so sánh precedence theo SemVer**.

Các luật precedence quan trọng của SemVer 2.0:

1. So sánh **major**, rồi **minor**, rồi **patch** dưới dạng số nguyên.
2. Với cùng **major.minor.patch**, **bản không có prerelease lớn hơn bản có prerelease**.
3. Với hai prereleases, so sánh từng identifier từ trái sang phải: các phần chỉ có chữ số được so sánh như số; identifier số có thứ tự thấp hơn identifier phi số; các identifier phi số so sánh theo thứ tự ASCII (có phân biệt hoa/thường).
4. **Build metadata sau + không ảnh hưởng precedence**. Ví dụ hai bản **1.2.3+ci.10** và **1.2.3+ci.11** có cùng precedence theo SemVer.
5. Những version như **1**, **1.2**, **1.2.3.4** không phải version SemVer 2.0 hợp lệ ở dạng chuẩn trên.

SemVer là một **hợp đồng phiên bản** do nhà phát hành áp dụng. Nó không tự chứng minh thư viện tương thích chỉ bằng cấu trúc số: phải đọc release notes, migration guide và kiểm thử tích hợp.

## 4. Maven không áp dụng nguyên xi SemVer 2.0

Tài liệu **Apache Maven POM Reference** mô tả version order và nói rõ thuật toán Maven **không tương thích hoàn toàn với SemVer 2.0**. Maven có điểm tương đồng khi các version tuân theo định dạng SemVer 1.0 đơn giản (đặc biệt với chữ thường), nhưng không coi mọi quy tắc SemVer 2.0 là chuẩn cho resolver.

Những khác biệt có hậu quả thực tế:

| Trường hợp | Kỳ vọng theo SemVer 2.0 | Maven version order |
| --- | --- | --- |
| **1.0.0** so với **1.0.0-rc1** | Release cao hơn prerelease | Maven cũng xếp release cao hơn qualifier rc |
| **1.0.0** so với **1.0.0-sp1** | sp1 là prerelease nên **thấp hơn** release | **sp** là qualifier “service pack” được Maven xếp **cao hơn** release |
| **1.0.0** so với **1.0.0-foo** | foo là prerelease nên **thấp hơn** release | Qualifier lạ được Maven xếp **sau các qualifier quen thuộc**, có thể **cao hơn release** |
| **1.2.3+build.1** và **1.2.3+build.2** | Có cùng precedence vì phần sau + bị bỏ qua | Maven **không đặc biệt bỏ qua** build metadata sau + |
| **1.0.0-rc1** và **1.0.0-RC1** | Identifier hoa/thường khác nhau, precedence có thể khác | Maven so sánh qualifier **không phân biệt hoa/thường** |
| **1.0**, **1.0.0** | **1.0** không đúng mẫu ba số chuẩn SemVer 2.0 | Maven thường coi **bằng nhau về thứ tự** |
| **1.0.0.0** | Không phải SemVer 2.0 chuẩn | Maven vẫn có thể so sánh và coi tương đương **1.0.0** |

**Cẩn thận với từ “bằng nhau”:** Maven có thể trả **compareTo == 0** cho hai version strings, nhưng **hai tọa độ artifact vẫn khác chuỗi version** và có đường dẫn khác trong repository. Một phiên bản **1.0** và một phiên bản **1.0.0** không được tự hiểu là “cùng một file JAR đã công bố”.

## 5. Maven tách chuỗi phiên bản thành các token như thế nào?

Đối với thuật toán phiên bản trong **Maven Artifact / ComparableVersion**, Maven không chỉ gọi hàm so sánh chuỗi ký tự toàn bộ. Nó xử lý các thành phần:

- **Dấu chấm .** phân tách version components.
- **Dấu gạch ngang -** và (theo POM Reference hiện hành) **dấu gạch dưới _** cũng là các dấu tách có ý nghĩa.
- **Chuyển tiếp giữa chữ và chữ số** cũng có thể tạo ranh giới token, ví dụ giữa **alpha** và **1**.
- Các token gồm chữ số ASCII **0–9** được xem là phần số, so sánh **theo giá trị số nguyên**, không so sánh từ điển.
- Token phi số được xét như qualifier. Maven có danh sách qualifier đã biết và quy tắc so sánh chuỗi riêng cho qualifier chưa biết.
- Dấu tách có thể có ý nghĩa khi so sánh số với qualifier hoặc khi các token khác kiểu; không được coi mọi dấu **.** và **-** là tương đương.

Ví dụ ý niệm:

~~~text
1.10          và 1.9
 -> 10 > 9 theo số, nên 1.10 > 1.9

1.0.0-foo2    và 1.0.0-foo10
 -> nhận diện phần 2 và 10, nên foo2 < foo10

1.0          và 1.0.0
 -> các thành phần .0 ở cuối có thể được chuẩn hóa bỏ đi
 -> hai chuỗi so sánh bằng nhau
~~~

Maven cũng chuẩn hóa những giá trị **“rỗng/không khác biệt”** ở cuối, ví dụ token số **0** hoặc alias release như **ga**, **final**. Vì thế **1**, **1.0**, **1.0.0**, **1-ga** có thể **so sánh bằng nhau**.

**Không áp dụng phép chuẩn hóa này cho việc đặt tên file, đường dẫn kho artifact hay migration scripts.** Tính bằng nhau về thứ tự của bộ so sánh không đồng nghĩa Maven tự đổi tên thư mục version dưới **~/.m2/repository**.

## 6. Qualifier order: quy tắc quyết định nhiều kết quả bất ngờ

Maven có thứ tự qualifier quen thuộc (từ thấp đến cao):

~~~text
alpha / a
   <
beta / b
   <
milestone / m
   <
rc / cr
   <
snapshot
   <
không có qualifier / ga / final / release
   <
sp
   <
qualifier không thuộc danh sách quen thuộc
~~~

Bảng này là **trật tự của qualifier trong so sánh Maven**, không phải workflow release mà mọi tổ chức bắt buộc theo.

| Qualifier | Ý nghĩa thường gặp | Vị trí tương đối trong Maven |
| --- | --- | --- |
| **alpha** | Bản rất sớm | Trước beta |
| **beta** | Bản thử nghiệm | Sau alpha, trước milestone |
| **milestone** | Mốc phát triển | Sau beta, trước rc |
| **rc** (alias **cr**) | Release candidate | Trước snapshot |
| **SNAPSHOT** | Development snapshot | Trước release không qualifier |
| **rỗng**; **ga**, **final**, **release** | Bản phát hành theo thứ tự comparator | Trước sp |
| **sp** | Service pack | Sau release |
| **foo**, **preview**, **redhat**, ... | Không có nghĩa đặc biệt theo quy tắc chuẩn | Xếp sau các qualifier đã biết, rồi so sánh chữ theo quy tắc không phân biệt hoa/thường |

Một số bí danh cần dùng đúng ngữ cảnh:

- **cr** tương đương **rc** trong quy tắc Maven.
- **ga/final/release** có thứ tự tương đương **không có qualifier**.
- **a**, **b**, **m** được nhận như dạng viết tắt của **alpha**, **beta**, **milestone** khi đi liền một số theo cú pháp mà bộ parser hỗ trợ, ví dụ **a1**, **b2**, **m3**. Không nên giả định một chữ **a** đứng độc lập luôn mang nghĩa alias alpha.
- **alpha1**, **beta2**, **rc3**, **foo10** thường được xử lý phần số theo thứ tự tự nhiên.

Quan trọng: **qualifier lạ không tự động là prerelease nhỏ hơn bản stable.** Nếu nhóm dùng tên **-preview**, **-customer**, **-hotfix** hoặc **-foo** tùy ý, Maven có thể xếp chúng theo thứ tự khác trực giác SemVer.

Nên đặt version theo quy ước rõ, dùng qualifier quen thuộc khi cần prerelease, và **thử bộ so sánh thật** khi gặp định dạng lạ.

## 7. Các cặp so sánh cụ thể

Các ví dụ tiêu biểu sau dựa trên quy tắc phiên bản Apache Maven:

| Version A | Quan hệ | Version B | Giải thích |
| --- | :---: | --- | --- |
| **1.9** | < | **1.10** | Numeric 9 < 10 |
| **1.0.0-alpha1** | < | **1.0.0-beta1** | alpha đứng trước beta |
| **1.0.0-beta1** | < | **1.0.0-m1** | beta trước milestone |
| **1.0.0-m1** | < | **1.0.0-rc1** | milestone trước rc |
| **1.0.0-rc1** | < | **1.0.0-SNAPSHOT** | rc trước snapshot |
| **1.0.0-SNAPSHOT** | < | **1.0.0** | snapshot trước release |
| **1.0.0** | < | **1.0.0-sp1** | sp lớn hơn release trong Maven |
| **1.0.0** | < | **1.0.0-foo** | foo là qualifier lạ, sau danh sách quen thuộc |
| **1.0.0-foo2** | < | **1.0.0-foo10** | Phần số 2 < 10 |
| **1.0.0** | = | **1.0** | Thành phần 0 ở cuối được chuẩn hóa |
| **1.0.0** | = | **1.0.0.0** | Thành phần số 0 dư có thể được chuẩn hóa |
| **1.0.0-rc1** | = | **1.0.0-RC1** | Maven so sánh qualifier không phân biệt hoa/thường |
| **1-ga** | = | **1-final** | Bí danh release trong comparator |

Ký hiệu **=** trong bảng chỉ nghĩa **quan hệ thứ tự do comparator trả về**, không phải là cùng artifact đã được publish, không phải cùng nội dung binary, và cũng không phải bằng nhau theo SemVer.

### Không nên rút gọn chỉ còn từ điển

Nếu sắp xếp chuỗi một cách thuần lexicographic, **1.10** thường đứng trước **1.9** vì ký tự đầu sau dấu chấm là 1 và 9. Kết quả đó **sai** so với numeric order của Maven. Tương tự, so sánh chữ nguyên vẹn **foo10** và **foo2** có thể dẫn đến kết quả ngược; Maven xử lý ranh giới chữ/số.

### Dấu gạch và dấu chấm không phải dấu trang trí

Maven POM Reference cho ví dụ kiểu **1.0.RC2 < 1.0-RC3 < 1.0.1**. Phần **.qualifier**, **-qualifier** và phần số có vị trí khác nhau trong kết quả. Tốt nhất nên viết **1.0.0-RC1** thay vì **1.0.0.RC1** để vừa giảm bất ngờ vừa rõ ý đồ prerelease.

## 8. “Bản prerelease luôn thấp hơn release” không đúng với mọi qualifier Maven

Theo SemVer 2.0, khi cùng **major.minor.patch** thì có prerelease **luôn có precedence thấp hơn** bản không có prerelease.

Nhưng Maven dành vị trí đặc biệt cho **sp** và những qualifier chưa biết:

~~~text
1.0.0-rc1   < 1.0.0
1.0.0       < 1.0.0-sp1
1.0.0       < 1.0.0-foo
~~~

Vì vậy, lối suy luận “mọi thứ sau dấu - đều là bản beta/prerelease” sai đối với Maven.

Nếu một thư viện được publish cả **2.0.0** và **2.0.0-preview**, không được mặc định resolver sẽ luôn coi **preview** là cũ hơn stable chỉ vì tên nghe như bản thử nghiệm. Một qualifier không thuộc danh sách đặc biệt có thể được Maven xếp cao hơn release.

Để quản lý artifacts quan trọng: nên dùng version release chuẩn (**x.y.z**) hoặc qualifier ổn định được công cụ hiểu, áp dụng version pins và kiểm tra dependency graph thật.

## 9. SNAPSHOT là khái niệm phân giải repository, không chỉ một qualifier

Trong Maven, **1.4.0-SNAPSHOT** thường chỉ một phiên bản phát triển có thể được publish nhiều lần khi đang làm việc. Repository có thể chứa **timestamped snapshots** liên quan tới base version ấy và metadata để resolver chọn artifact thực tế theo update policy.

Cần tách ba điều:

1. **Comparator:** với cùng base, **1.4.0-SNAPSHOT < 1.4.0** theo qualifier order.
2. **Repository resolution:** khi Maven cần dependency **1.4.0-SNAPSHOT**, repository metadata và chính sách cập nhật có thể làm artifact được tải thay đổi theo thời gian.
3. **Reproducible build:** chỉ ghi chuỗi **1.4.0-SNAPSHOT** trong POM không cam kết hai lần build ở hai thời điểm luôn lấy đúng cùng bytes.

**SNAPSHOT không phải một định danh build bất biến.** Nếu pipeline release phải lặp lại chính xác, nên dùng các versions phát hành cố định, giữ lại checksum/artifact provenance và tránh phụ thuộc snapshot động ở những phần bắt buộc ổn định.

Một timestamped artifact của snapshot cũng không có nghĩa là một bản SemVer ổn định chỉ vì tên chứa ngày tháng. Để biết bytes nào đã được dùng, xem logs resolution, repository metadata, dependency tree và artifact checksum.

## 10. Version range: cú pháp và ý nghĩa

Một dependency có thể được khai báo version cụ thể hoặc **version requirement/range**. Với Maven, dấu ngoặc quyết định cận đóng hoặc mở:

| Cú pháp | Ý nghĩa theo Maven |
| --- | --- |
| **1.3** | Soft requirement ở 1.3; các ràng buộc/mediation khác có thể dẫn đến version khác |
| **[1.3]** | Hard requirement chính xác version 1.3 |
| **[1.2,1.5]** | Từ 1.2 đến 1.5, gồm hai đầu |
| **[1.2,1.5)** | Từ 1.2 (gồm) tới trước 1.5 |
| **(1.2,1.5]** | Lớn hơn 1.2, không gồm 1.2; tới 1.5 gồm |
| **[1.5,)** | Từ 1.5 trở lên, không có cận trên |
| **(,2.0]** | Không có cận dưới, tới 2.0 gồm |
| **(,1.1),(1.1,)** | Cho phép mọi phiên bản trừ 1.1 theo thứ tự so sánh |
| **[1.0,2.0)** | Từ 1.0 trở lên tới trước 2.0, **nhưng lưu ý prerelease của 2.0** |

Ví dụ dependency dùng range:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>sample-api</artifactId>
    <version>[1.2,2.0)</version>
</dependency>
~~~

**org.example:sample-api** trong ví dụ chỉ là tọa độ minh họa; không khẳng định artifact này tồn tại trên Maven Central. XML chỉ minh họa syntax, chưa phải full POM.

Maven chọn version phù hợp **các hard requirements** từ danh sách ứng viên phân giải được; nếu không có version thỏa hard constraints, build sẽ thất bại. Kết quả còn phụ thuộc phiên bản có thật ở repositories, cấu hình cập nhật, dependency graph và mediation; **không thể suy ra một version chính xác chỉ từ range mà không biết repository metadata**.

### Bẫy nổi tiếng: [1.0,2.0) có thể nhận 2.0-rc1

Theo comparator:

~~~text
2.0-rc1 < 2.0
~~~

Vì vậy **2.0-rc1** nằm dưới cận trên **2.0** và có thể thuộc range **[1.0,2.0)**. Người đọc đôi khi tưởng range này nghĩa là “chỉ phiên bản major 1”. Nó thực chất là **khoảng thứ tự**, không phải bộ lọc phiên bản major theo SemVer.

Apache Maven POM Reference lưu ý trường hợp này và đề cập cách dùng giới hạn khác như **[1,2-alpha)** trong những chính sách cụ thể. Tuy nhiên, các qualifier lạ và version formats phi chuẩn vẫn có thể gây bất ngờ. Đừng hứa một range rộng sẽ **loại tất cả bản 2.x prerelease** khi chưa thực nghiệm trên danh sách versions thật.

**Khuyến nghị quan trọng:** với build sản phẩm/CI cần tái tạo, dùng phiên bản cụ thể được duyệt trong **dependencyManagement/BOM**, nâng cấp có kiểm soát và xác minh dependency graph, thay vì chọn range rộng chỉ để “tự lấy latest”.

## 11. Maven không luôn chọn version cao nhất trong dependency graph

Nhiều người nhầm hai việc:

- **Version comparison:** xác định A cao, thấp hoặc bằng B.
- **Dependency mediation:** khi có nhiều đường dependency dẫn tới các version khác nhau của **cùng artifact**, Maven quyết định version nào tham gia classpath.

Với các khai báo dependency version thông thường, Maven sử dụng quy tắc **nearest definition**: một version xuất hiện ở đường dependency gần root hơn có thể được chọn **dù số version thấp hơn**. Khi có nhiều candidate cùng độ sâu, thứ tự khai báo có thể quyết định kết quả.

Ví dụ graph minh họa:

~~~text
my-app
├── lib-a:1.0
│   └── common-util:2.7
└── lib-b:1.0
    └── common-util:2.9
~~~

Hai candidate **common-util:2.7** và **common-util:2.9** có cùng độ sâu. **Không được tự kết luận Maven nhất định chọn 2.9 vì cao hơn**. Mediation có thể theo đường khai báo xuất hiện trước. Nếu root **my-app** khai báo trực tiếp **common-util:2.7**, version trực tiếp có ưu tiên gần root hơn, bất kể một thư viện transitively muốn 2.9.

**dependencyManagement** trong POM của ứng dụng hoặc parent có thể cung cấp version policy cho artifact, giúp tránh phụ thuộc vào thứ tự tình cờ của cây dependency. Nếu dùng **BOM import**, chỉ tập managed dependencies được nhập, không đồng nghĩa version được cập nhật tự động theo SemVer.

Hãy dùng:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.example:common-util
mvn help:effective-pom
~~~

Lệnh **dependency:tree** có thể cần tải plugin nếu chưa có cache. Trong ví dụ giả định **org.example:common-util** không nhất thiết tồn tại, nên lệnh includes chỉ có ý nghĩa sau khi thay tọa độ bằng artifact thật trong project.

**Tóm lại:** highest-by-comparator là vấn đề riêng, còn version thực tế Maven chọn từ dependency graph chịu ảnh hưởng của nearest-wins, hard version requirements và management. Không được thay thế cả hệ thống resolver bằng một thao tác sort đơn giản.

## 12. Artifact identity: bằng nhau về compareTo không có nghĩa chung tọa độ

Giả sử repository có hai POM/JAR dưới:

~~~text
~/.m2/repository/org/example/api/1.0/api-1.0.jar
~/.m2/repository/org/example/api/1.0.0/api-1.0.0.jar
~~~

Bộ so sánh Maven có thể cho:

~~~text
ComparableVersion("1.0").compareTo(ComparableVersion("1.0.0")) == 0
~~~

Nhưng **org.example:api:1.0** và **org.example:api:1.0.0** là **hai tọa độ khai báo khác nhau về version string**. Không được giả định có một cơ chế tự động đổi tên và trỏ tới một file chung trong local repository. Nếu chỉ một version đã được publish, chỉ dùng compareTo không thể đảm bảo version còn lại cũng có artifact.

Điều tương tự áp dụng cho các cách viết **1-ga**, **1-final**, **1.0**, **1**: chúng có thể ngang thứ tự, nhưng không có hợp đồng nào đảm bảo các đường dẫn repository chứa cùng bytes.

Quy tắc thực hành:

- **So sánh thứ tự:** dùng comparator.
- **Xác định artifact tham chiếu:** dùng chính xác tọa độ.
- **Phân giải artifacts:** dùng Maven Resolver và repository metadata.
- **Xác nhận nội dung:** dùng checksum/provenance, không dùng “version trông tương đương”.

## 13. Ví dụ Java 17 chạy được: sử dụng ComparableVersion

Để tránh đoán thứ tự, chúng ta có thể viết chương trình Java sử dụng **org.apache.maven.artifact.versioning.ComparableVersion** của thư viện **maven-artifact**. Đây là API để minh họa comparator Maven, **không phải một dependency bắt buộc cho mọi ứng dụng Java**.

Ví dụ pin **maven-artifact:3.9.9**, JDK 17+, Maven 3.9+ và dùng Exec Maven Plugin để chạy main method.

### 13.1. Cấu trúc dự án

~~~text
maven-version-order-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/versions/VersionOrderDemo.java
    └── test/java/com/example/versions/VersionOrderTest.java
~~~

### 13.2. pom.xml hoàn chỉnh

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-version-order-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.maven</groupId>
            <artifactId>maven-artifact</artifactId>
            <version>3.9.9</version>
        </dependency>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Lưu ý:** **maven-artifact** là thư viện của Maven được đưa vào classpath của ví dụ này để **gọi comparator trực tiếp**. Việc dùng API của Maven trong ứng dụng bình thường chỉ để so sánh version nên được cân nhắc; nếu chỉ cần POM dependency resolution, Maven đã làm việc đó trong build và ứng dụng không cần import API này.

### 13.3. Main class để in kết quả so sánh

Tạo **src/main/java/com/example/versions/VersionOrderDemo.java**:

~~~java
package com.example.versions;

import org.apache.maven.artifact.versioning.ComparableVersion;

public final class VersionOrderDemo {

    private VersionOrderDemo() {
    }

    public static int compare(String left, String right) {
        ComparableVersion a = new ComparableVersion(left);
        ComparableVersion b = new ComparableVersion(right);
        return Integer.signum(a.compareTo(b));
    }

    private static void show(String left, String right) {
        int value = compare(left, right);
        String sign = value < 0 ? "<" : value > 0 ? ">" : "=";
        System.out.println(left + " " + sign + " " + right);
    }

    public static void main(String[] args) {
        show("1.9", "1.10");
        show("1.0.0-alpha1", "1.0.0-beta1");
        show("1.0.0-beta1", "1.0.0-rc1");
        show("1.0.0-rc1", "1.0.0");
        show("1.0.0", "1.0.0-sp1");
        show("1.0.0", "1.0.0-foo");
        show("1.0", "1.0.0");
        show("1.0.0-rc1", "1.0.0-RC1");
        show("1.0.0-foo2", "1.0.0-foo10");

        boolean sameOrder =
                compare("1.0.0+build.1", "1.0.0+build.2") == 0;
        System.out.println("Maven ignores +build metadata: " + sameOrder);
    }
}
~~~

Hàm **compare** trả -1, 0 hoặc 1 theo kết quả compareTo. Nó không định nghĩa lại version rules, mà gọi chính ComparableVersion. Hàm **show** in ký hiệu <, = hoặc >.

### 13.4. JUnit 5 test xác nhận các quy tắc quan trọng

Tạo **src/test/java/com/example/versions/VersionOrderTest.java**:

~~~java
package com.example.versions;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class VersionOrderTest {

    @Test
    void numericSegmentsAreComparedNumerically() {
        assertTrue(VersionOrderDemo.compare("1.9", "1.10") < 0);
    }

    @Test
    void releaseAliasesAndTrailingZerosCanCompareEqual() {
        assertEquals(0, VersionOrderDemo.compare("1", "1.0.0"));
        assertEquals(0, VersionOrderDemo.compare("1-ga", "1"));
    }

    @Test
    void knownQualifiersFollowMavenOrdering() {
        assertTrue(VersionOrderDemo.compare("1.0.0-rc1", "1.0.0") < 0);
        assertTrue(VersionOrderDemo.compare("1.0.0", "1.0.0-sp1") < 0);
    }

    @Test
    void unexpectedSemverAssumptionsAreDetected() {
        assertTrue(VersionOrderDemo.compare("1.0.0", "1.0.0-foo") < 0);
        assertEquals(0,
                VersionOrderDemo.compare("1.0.0-rc1", "1.0.0-RC1"));
        assertNotEquals(0,
                VersionOrderDemo.compare(
                        "1.0.0+build.1", "1.0.0+build.2"));
    }
}
~~~

Test cuối đặc biệt quan trọng: nó không cố kiểm thử SemVer bằng code của Maven, mà **đánh dấu những điểm khác với giả định SemVer**. Bản build demo không cần nguồn Internet sau khi Maven đã tải đầy đủ plugin/dependencies vào cache tương thích, nhưng lần đầu có thể phải phân giải artifacts từ repositories.

### 13.5. Lệnh chạy và đầu ra

Từ thư mục **maven-version-order-demo**:

~~~bash
mvn -version
mvn clean test
mvn -q compile exec:java -Dexec.mainClass=com.example.versions.VersionOrderDemo
~~~

Lệnh thứ hai chạy **bốn test JUnit**, dự kiến **0 failures, 0 errors** khi môi trường và dependencies bình thường. Lệnh cuối gọi **Exec Maven Plugin** để chạy class Java cùng classpath mà Maven đã dựng, không phải tự cấu hình classpath thủ công.

**Các dòng stdout từ chương trình main**:

~~~text
1.9 < 1.10
1.0.0-alpha1 < 1.0.0-beta1
1.0.0-beta1 < 1.0.0-rc1
1.0.0-rc1 < 1.0.0
1.0.0 < 1.0.0-sp1
1.0.0 < 1.0.0-foo
1.0 = 1.0.0
1.0.0-rc1 = 1.0.0-RC1
1.0.0-foo2 < 1.0.0-foo10
Maven ignores +build metadata: false
~~~

**Đây là output của main method**, không bao gồm mọi log do Maven/Exec Plugin có thể in. Đặt **-q** nhằm giảm Maven logs, không có nghĩa mọi môi trường sẽ chỉ hiển thị đúng 10 dòng và không có một cảnh báo nào khác.

Nếu Maven artifact library được nâng cấp, hãy chạy lại tests; chính bộ so sánh phiên bản đang dùng là thứ cần kiểm tra, không nên coi thứ tự là bất biến giữa mọi bản công cụ trong tương lai.

## 14. Cách kiểm thử thứ tự phiên bản ngay trong Maven distribution

Apache Maven POM Reference mô tả công cụ version-order testing nằm trong bản phân phối Maven và có thể được gọi thông qua file **maven-artifact-<version>.jar** trong thư mục **lib** (khi file JAR đó có entrypoint tương ứng).

Ví dụ cú pháp minh họa trên bản distribution thích hợp:

~~~bash
java -jar /path/to/apache-maven/lib/maven-artifact-3.9.9.jar 1 1.0 1.0.0
~~~

**Đường dẫn này là ví dụ**, không phải lệnh copy nguyên xi ở mọi OS hoặc mọi Maven installation. Bạn phải xác định vị trí/phiên bản thực tế của Maven Artifact JAR; các bản phân phối hoặc cách cài Maven khác nhau có thể có layout khác. Phương án Java ở phần 13 rõ ràng hơn nếu cần chạy kiểm thử theo dependency version đã pin trong project.

Khi cần so sánh **nhiều cặp phiên bản lạ**, việc chạy comparator thật tốt hơn suy luận chỉ dựa trên văn bản SemVer.

## 15. Cách kiểm tra version thực tế được resolver chọn

Đối với dự án Maven có dependencies thật, hãy kiểm tra bằng công cụ dành cho dependency graph:

~~~bash
mvn help:effective-pom
mvn dependency:tree
mvn dependency:tree -Dincludes=org.apache.commons:commons-lang3
~~~

- **effective-pom** cho thấy dependency/dependencyManagement/plugin configuration đã hợp nhất từ parent và active profiles.
- **dependency:tree** cho biết những dependency thực tế ở đường cây và version được chọn; nhiều plugin versions còn có options để hiển thị thông tin phiên bản bị bỏ qua.
- **includes** lọc tên artifact cần điều tra. Trong ví dụ hãy thay bằng tọa độ đúng của dự án.
- Với **SNAPSHOT/ranges**, kiểm tra repository và update policy; đầu ra ở hai thời điểm có thể khác.
- **-U** có thể thay đổi hành vi cập nhật metadata/SNAPSHOT theo chính sách Maven; không nên nhầm với “nâng cấp tất cả dependencies lên version cao nhất”.

Nếu nghi một dependency có thể bị đổi version vì BOM import hoặc parent dependencyManagement, hãy xem **effective-pom** trước, rồi đối chiếu **dependency:tree** và log resolution. Đừng chỉ nhìn khai báo trực tiếp trong một module con.

### Parent version, plugin version và dependency version cũng cần pin

Một build có thể pin version ứng dụng nhưng dùng plugin không pin. Khi đó thay đổi môi trường hoặc repository vẫn có thể ảnh hưởng kết quả build. Nên quản lý versions của compiler, Surefire/Failsafe, JAR plugin, dependencies và parent BOM nhất quán theo chính sách project.

**SemVer không tự làm build reproducible.** Tính tái tạo cần phụ thuộc cố định, artifact provenance, cấu hình Maven/JDK, repository, plugin versions và môi trường phù hợp.

## 16. Quy tắc lựa chọn version trong dự án thật

Một checklist thực tế:

1. **Xác định artifact** theo **groupId:artifactId[:type[:classifier]]** và version cần giải quyết; đừng chỉ đọc số version rời khỏi artifact identity.
2. **Phân biệt chính xác version và range.** Nếu dùng range, viết rõ cận đóng/mở và hiểu qualifier ngay sát cận.
3. **Không coi mọi version là SemVer 2.0 hợp lệ.** Maven cho phép thêm phần số, các qualifier và cách viết khác.
4. **Không coi mọi suffix sau - là prerelease cũ hơn stable.** Xem danh sách qualifier quen thuộc và vị trí của qualifier lạ.
5. **Không giả định build metadata sau + bị bỏ qua** trong Maven comparator.
6. **Không dựa vào case-sensitive comparison** kiểu SemVer cho Maven; tránh qualifiers trộn hoa/thường.
7. **Không coi compareTo == 0 là cùng artifact.** Kiểm tra version string cụ thể và repository coordinates.
8. **Xác minh chính sách SNAPSHOT.** Snapshot động không phải immutable release.
9. **Dùng dependencyManagement/BOM cho versions được duyệt** ở multi-module builds; ưu tiên quản lý nâng cấp có kiểm thử.
10. **Kiểm tra mediation.** Nearest definition và quản lý dependency có thể quan trọng hơn chuyện version nào có số cao nhất.
11. **Giữ riêng quan hệ tương thích API và thứ tự so sánh.** Major bump là lời cam kết của publisher nếu họ áp dụng SemVer, không phải quy tắc Maven cưỡng chế.
12. **Kiểm thử comparator thực** cho những chuỗi lạ như version có qualifier vendor hoặc metadata.
13. **Đọc release notes/migration guide** trước khi nâng minor/major, nhất là với framework/plugin lớn.
14. **So sánh classpath cuối** bằng dependency tree và kiểm thử ứng dụng, không chỉ kiểm tra POM XML.
15. **Pin build tool/plugins và kiểm tra output** trên CI cho các release artifacts quan trọng.

## 17. Các lỗi phổ biến khi giả định Maven tuân thủ SemVer

| Hiện tượng | Giả định sai | Cách xử lý |
| --- | --- | --- |
| Version **1.10** bị coi cũ hơn **1.9** trong script | So sánh chuỗi bằng lexical sort | Dùng ComparableVersion hoặc comparator phù hợp |
| **1.0.0-foo** bị coi là prerelease thấp hơn **1.0.0** | Áp dụng luật SemVer 2.0 cho qualifier lạ | Kiểm tra Maven qualifier ordering |
| **1.0.0-sp1** được chọn dù chỉ định thích bản stable | Tưởng mọi hậu tố -xxx đều thấp hơn stable | Coi **sp** là Maven qualifier cao hơn release |
| **1.0.0+ci.1** và **1.0.0+ci.2** được coi khác thứ tự | Tưởng Maven bỏ qua +build metadata | Đừng dùng + như bằng chứng precedence theo SemVer |
| **1.0** và **1.0.0** so sánh bằng nhau | Tưởng mỗi chuỗi là một rank hoàn toàn khác | Phân biệt so sánh với artifact identity |
| Khai báo **[1.0,2.0)** vẫn nhận **2.0-rc1** | Hiểu range là “mọi major 1” | Kiểm tra cận theo Maven comparator |
| Dependency version thấp hơn được chọn | Tưởng Maven luôn chọn highest version | Kiểm tra nearest-wins, dependencyManagement, BOM |
| Artifact đổi giữa hai lần CI dù POM giữ nguyên | Phụ thuộc SNAPSHOT/range/update metadata | Dùng version releases được pin/provenance |
| Local máy A thành công, CI lỗi với version khác | Profiles/settings/repos/mirrors cập nhật khác | So sánh effective POM, tree, Maven/JDK |
| Dependency tree không có version mong đợi | Version managed bởi parent/BOM | Kiểm tra effective dependencyManagement |
| Release nâng minor làm API không tương thích | Tin tuyệt đối publisher tuân SemVer | Đọc changelog và chạy integration tests |
| Tool ngoài Maven sắp xếp khác Maven | Mỗi ecosystem có luật riêng | Dùng comparator phù hợp với hệ thống sẽ phân giải |

## 18. Bài tập tự kiểm tra

**Câu 1:** Trong Maven, **1.0.0-alpha1** và **1.0.0-beta1** bản nào đứng sau?

**Đáp:** **1.0.0-beta1** đứng sau vì beta cao hơn alpha theo thứ tự qualifier quen thuộc.

**Câu 2:** **1.0.0-rc1 < 1.0.0** có đúng không?

**Đáp:** Đúng theo Maven; qualifier rc đứng trước không có qualifier.

**Câu 3:** **1.0.0-sp1** có đứng trước **1.0.0** vì có dấu - không?

**Đáp:** Không. Maven có thứ tự đặc biệt **sp > release**, khác luật prerelease của SemVer 2.0.

**Câu 4:** Maven compare **1.0.0** với **1.0** ra 0. Có chắc repository của cả hai version đều chứa cùng JAR?

**Đáp:** Không. compareTo == 0 chỉ nói về thứ tự; artifact version string và repository path có thể khác.

**Câu 5:** Theo SemVer 2.0, **1.2.3+ci.1** và **1.2.3+ci.2** khác precedence?

**Đáp:** Không; SemVer bỏ qua build metadata. Nhưng Maven comparator không áp dụng nguyên xi quy tắc này.

**Câu 6:** Range **[1.0,2.0)** có thể nhận **2.0-rc1** không?

**Đáp:** Có. Vì **2.0-rc1 < 2.0**, nó có thể nằm dưới cận trên mở.

**Câu 7:** Hai thư viện transitively yêu cầu cùng artifact ở **2.7** và **2.9**. Maven luôn chọn 2.9?

**Đáp:** Không. Dependency mediation có quy tắc nearest definition, thứ tự khai báo và có thể bị quản lý bởi dependencyManagement/hard requirements.

**Câu 8:** Dùng **1.4.0-SNAPSHOT** trong release POM có đảm bảo build lặp lại ra cùng bytes?

**Đáp:** Không. SNAPSHOT thường là artifact thay đổi theo thời điểm và repository metadata.

**Câu 9:** Có thể dùng chuỗi **1.2.3.4** làm Maven version không?

**Đáp:** Maven có thể so sánh chuỗi có nhiều numeric components; điều này không đồng nghĩa nó là SemVer 2.0 hợp lệ.

**Câu 10:** Nếu một thư viện được đặt version **3.0.0** thì chắc chắn API đã phá vỡ tương thích ngược?

**Đáp:** Không. Đó là quy ước semantic mà nhà phát hành có thể tuân hoặc không. Maven chỉ phân giải theo tọa độ và luật version, không chứng minh nội dung API.

## Tài liệu tham khảo

- [Apache Maven — POM Reference: Dependency Version Requirement Specification và Version Order Specification](https://maven.apache.org/pom.html#version-order-specification)
- [Apache Maven — POM Reference: version requirements](https://maven.apache.org/pom.html#dependency-version-requirement-specification)
- [Apache Maven Artifact API — ComparableVersion](https://maven.apache.org/ref/3-LATEST/apidocs/org/apache/maven/artifact/versioning/ComparableVersion.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Semantic Versioning 2.0.0 Specification](https://semver.org/spec/v2.0.0.html)
- [Apache Maven — Introduction to Repositories](https://maven.apache.org/guides/introduction/introduction-to-repositories.html)
