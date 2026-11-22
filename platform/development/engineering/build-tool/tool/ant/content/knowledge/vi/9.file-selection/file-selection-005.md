# Phân biệt chữ hoa, chữ thường và cách xử lý liên kết tượng trưng

Trong Apache Ant, việc chọn tệp thường được mô tả bằng phần tử **FileSet**. Một tập tệp xác định thư mục gốc, các mẫu đường dẫn được bao gồm và các mẫu bị loại trừ. Khi build chạy trên nhiều hệ điều hành hoặc làm việc với thư mục có symbolic link, hai thiết lập cần được hiểu rõ là **độ phân biệt chữ hoa, chữ thường** (**casesensitive**) và **cách theo liên kết tượng trưng** (**followsymlinks**).

Hai thiết lập này ảnh hưởng trực tiếp đến những tệp mà task như **copy**, **delete**, **zip** hoặc **jar** nhận được. Nếu không cấu hình có chủ đích, cùng một build file có thể chọn tập tệp khác nhau giữa máy Windows, macOS, Linux hoặc giữa các workspace có cấu trúc liên kết khác nhau.

## 1. Ant chọn tệp bằng pattern

Một **fileset** xác định tập tệp tương đối với một thư mục gốc:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</fileset>
~~~

Trong ví dụ:

- **dir="src"** là thư mục gốc để Ant quét.
- **include** chọn các tệp có đường dẫn phù hợp với mẫu.
- **exclude** loại các đường dẫn không mong muốn khỏi tập kết quả.
- Các mẫu được so khớp với đường dẫn tương đối từ thư mục gốc của fileset.

Ant hỗ trợ các ký tự đại diện thường dùng:

| Mẫu | Ý nghĩa |
|---|---|
| <code>*</code> | Khớp không hoặc nhiều ký tự trong một cấp đường dẫn, không vượt qua dấu phân cách thư mục |
| <code>?</code> | Khớp đúng một ký tự trong một cấp đường dẫn |
| <code>**</code> | Khớp không hoặc nhiều cấp thư mục |
| <code>**/*.java</code> | Khớp tệp Java ở thư mục gốc hoặc bất kỳ thư mục con nào |
| <code>src/**/test-*.xml</code> | Khớp tệp XML có tên bắt đầu bằng **test-** dưới cây thư mục **src** |

Ví dụ, với cấu trúc:

~~~text
project/
└── src/
    ├── Main.java
    ├── README.md
    └── test/
        ├── UserTest.java
        └── test-config.xml
~~~

Mẫu <code>**/*.java</code> chọn **Main.java** và **test/UserTest.java**. Mẫu <code>**/test-*.xml</code> chọn **test/test-config.xml**.

Có thể viết mẫu trực tiếp trong thuộc tính **includes**/**excludes** hoặc khai báo từng mẫu bằng phần tử lồng nhau. Cách lồng nhau thường dễ đọc và bảo trì hơn khi có nhiều điều kiện:

~~~xml
<fileset dir="src">
    <include name="**/*.java"/>
    <include name="**/*.properties"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/*Test.java"/>
</fileset>
~~~

Nếu một đường dẫn khớp cả include lẫn exclude, quy tắc exclude sẽ loại đường dẫn đó khỏi kết quả. Điều này cho phép chọn rộng trước rồi loại các nhóm không cần thiết.

## 2. Phân biệt chữ hoa và chữ thường với casesensitive

Thuộc tính **casesensitive** của **fileset** quyết định việc Ant so khớp tên đường dẫn với include/exclude pattern có phân biệt chữ hoa và chữ thường hay không.

Giá trị mặc định là **true**:

~~~xml
<fileset dir="docs" casesensitive="true">
    <include name="**/*.md"/>
</fileset>
~~~

Với cấu hình này, mẫu <code>**/*.md</code> được so khớp đúng chữ hoa, chữ thường. Tệp có tên **guide.md** phù hợp, còn **Guide.MD** không phù hợp với mẫu trên nếu tên được quét có cách viết khác.

Nếu đặt **casesensitive="false"**, Ant so khớp không phân biệt hoa thường:

~~~xml
<fileset dir="docs" casesensitive="false">
    <include name="**/*.md"/>
</fileset>
~~~

Khi đó, các tên như **guide.md**, **Guide.MD** hoặc **GUIDE.Md** đều có thể khớp mẫu.

### Tác động của hệ điều hành và filesystem

Cần phân biệt hai lớp:

1. **Filesystem** quyết định cách hệ điều hành tra cứu tên tệp và thư mục.
2. **Ant pattern matching** quyết định mẫu include/exclude có so khớp phân biệt hoa thường hay không.

Các filesystem phổ biến không có cùng hành vi:

| Môi trường thường gặp | Hành vi tên tệp thường thấy |
|---|---|
| Windows với NTFS theo cấu hình mặc định | Tra cứu thường không phân biệt hoa thường, nhưng vẫn giữ cách viết tên |
| Linux với ext4 và nhiều filesystem Unix | Phân biệt hoa thường |
| macOS với APFS mặc định trên nhiều máy | Thường không phân biệt hoa thường |
| macOS với volume được định dạng case-sensitive | Phân biệt hoa thường |

Đây là hành vi phổ biến, không phải cam kết cho mọi máy: cấu hình volume, filesystem và công cụ có thể khác nhau.

Ví dụ, một repository có thể chứa tệp **Readme.MD**. Trên filesystem phân biệt hoa thường, mẫu <code>**/*.md</code> với **casesensitive="true"** không khớp tên đó. Trên máy khác, người phát triển có thể không nhận ra vấn đề nếu họ luôn tạo tên tệp viết thường.

Thiết lập **casesensitive="false"** làm cho quy tắc so khớp của Ant ít phụ thuộc cách viết hoa thường hơn:

~~~xml
<copy todir="build/docs">
    <fileset dir="docs" casesensitive="false">
        <include name="**/*.md"/>
    </fileset>
</copy>
~~~

Tuy nhiên, thiết lập này **không thay đổi khả năng của filesystem**. Nó không cho phép Windows lưu hai tệp khác nhau chỉ khác chữ hoa thường trong cùng một thư mục nếu filesystem không hỗ trợ; cũng không đổi tên tệp đã chọn. Khi copy hoặc đóng gói, cách viết tên thực tế vẫn được lấy từ đường dẫn nguồn.

### Khi nào nên dùng true hoặc false?

Dùng **casesensitive="true"** khi quy ước tên tệp của dự án yêu cầu khớp chính xác, hoặc khi phân biệt tên như **Config.xml** và **config.xml** là có ý nghĩa.

Dùng **casesensitive="false"** khi pattern được thiết kế để chọn theo phần mở rộng hoặc quy tắc tên không phụ thuộc cách viết hoa thường, ví dụ chọn mọi tài liệu Markdown hoặc mọi tệp ảnh bất kể chữ hoa trong phần mở rộng.

Điều quan trọng là dùng cùng một quy tắc trong các build chạy trên máy cá nhân và CI. Nếu không, một số tệp có thể được đưa vào gói trên máy này nhưng bị bỏ qua trên máy khác.

## 3. Include, exclude và case sensitivity

Độ phân biệt hoa thường áp dụng cho việc so khớp các mẫu include và exclude. Vì vậy, cần xem cả hai nhóm khi cấu hình.

~~~xml
<fileset dir="src" casesensitive="false">
    <include name="**/*.JAVA"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/*test.java"/>
</fileset>
~~~

Với **casesensitive="false"**:

- **Main.java** và **Main.JAVA** đều có thể khớp include <code>**/*.JAVA</code>.
- **UserTest.java** có thể khớp exclude <code>**/*test.java</code>.
- Tệp trong thư mục **generated** bị loại dù tên thư mục thực tế có cách viết hoa khác.

Nếu đặt **casesensitive="true"**, mỗi pattern phải khớp cách viết hoa thường của đường dẫn được quét.

Có thể chọn theo phần mở rộng không phân biệt hoa thường, đồng thời loại các tệp kiểm thử:

~~~xml
<fileset dir="src" casesensitive="false">
    <include name="**/*.java"/>
    <exclude name="**/*test.java"/>
    <exclude name="**/generated/**"/>
</fileset>
~~~

Khi cần một quy tắc tên chính xác, nên giữ **casesensitive="true"** và viết pattern đúng theo quy ước đặt tên của repository. Không nên bật không phân biệt hoa thường một cách máy móc nếu dự án cố ý sử dụng hai tên khác nhau chỉ bởi chữ hoa/thường.

## 4. Liên kết tượng trưng là gì?

Symbolic link (symlink) là một mục trong filesystem trỏ tới một tệp hoặc thư mục khác. Nó có tên và vị trí trong cây thư mục, nhưng nội dung thực tế nằm ở đích mà liên kết tham chiếu.

Ví dụ trên Linux hoặc macOS:

~~~bash
ln -s ../shared/config config-link
~~~

Cấu trúc có thể trông như sau:

~~~text
project/
├── build.xml
├── src/
│   └── Main.java
├── shared/
│   └── config/
│       └── app.properties
└── config-link -> ../shared/config
~~~

Thư mục **config-link** là liên kết đến **shared/config**. Khi công cụ đi theo liên kết, nó có thể nhìn thấy **app.properties** thông qua đường dẫn **config-link/app.properties**.

Symlink hữu ích khi nhiều dự án dùng chung một thư mục tài nguyên hoặc khi muốn trỏ một tên ổn định đến vị trí được quản lý ở nơi khác. Nhưng trong quy trình build, việc tự động đi theo symlink cũng có thể làm Ant quét thêm dữ liệu nằm ngoài thư mục dự án, đi vào cây thư mục không dự kiến hoặc gặp cấu trúc vòng.

## 5. Điều khiển việc theo symlink bằng followsymlinks

Thuộc tính **followsymlinks** của **fileset** xác định Ant có đi theo symbolic link khi quét thư mục hay không. Giá trị mặc định là **true**.

~~~xml
<fileset dir="src" followsymlinks="true">
    <include name="**/*.java"/>
</fileset>
~~~

Với mặc định này, Ant có thể đi theo liên kết tượng trưng khi quét và chọn nội dung ở đích liên kết nếu phù hợp với pattern.

Để không đi theo symlink, đặt **followsymlinks="false"**:

~~~xml
<fileset dir="src" followsymlinks="false">
    <include name="**/*.java"/>
</fileset>
~~~

Khi đó, Ant không đi vào các thư mục thông qua symbolic link và không đưa các mục liên kết vào tập tệp được quét theo hành vi follow-link của FileSet. Tệp hoặc thư mục thực tại vị trí đích vẫn có thể được chọn nếu nó nằm trong cây thư mục được quét trực tiếp theo đường dẫn thông thường.

### Ví dụ với copy

Giả sử thư mục **src** có một symlink **shared** trỏ tới thư mục tài nguyên dùng chung. Nếu chỉ muốn copy các tệp nằm trong cây thư mục thật của **src**, có thể viết:

~~~xml
<copy todir="build/resources">
    <fileset dir="src"
             includes="**/*.properties"
             followsymlinks="false"/>
</copy>
~~~

Nếu muốn Ant đi theo liên kết để lấy tài nguyên được chia sẻ, có thể đặt rõ:

~~~xml
<copy todir="build/resources">
    <fileset dir="src"
             includes="**/*.properties"
             followsymlinks="true"/>
</copy>
~~~

Nên ghi rõ giá trị trong build file khi hành vi symlink ảnh hưởng tới nội dung artifact. Điều này giúp người đọc nhận ra quyết định đó thay vì phải dựa vào mặc định của Ant.

## 6. Symlink có thể làm thay đổi phạm vi dữ liệu được build

Một liên kết trong thư mục nguồn có thể trỏ ra ngoài thư mục gốc của fileset:

~~~text
workspace/
├── project/
│   └── src/
│       ├── Main.java
│       └── private-data -> ../../shared-private/
└── shared-private/
    └── credentials.properties
~~~

Nếu FileSet theo symlink và pattern chọn mọi tệp properties, nội dung ở đích liên kết có thể lọt vào tập dữ liệu. Điều này có thể dẫn tới:

- Đưa nhầm tệp cấu hình hoặc dữ liệu riêng vào JAR/ZIP.
- Đóng gói các tệp lớn ngoài phạm vi dự án.
- Build phụ thuộc vào một thư mục chỉ tồn tại trên máy developer.
- Kết quả khác nhau giữa máy có symlink và máy checkout không có symlink.
- Quét lặp dữ liệu hoặc gặp vòng liên kết trong cây thư mục phức tạp.

Với tác vụ đóng gói hoặc copy tài nguyên phát hành, nếu dự án không có yêu cầu theo symlink, nên cân nhắc đặt **followsymlinks="false"** và khai báo include/exclude rõ ràng.

Nếu cần theo symlink, cần kiểm soát đích liên kết: xác nhận thư mục đích nằm trong phạm vi cho phép, không trỏ đến dữ liệu bí mật hoặc thư mục thay đổi ngoài kiểm soát của build, và tránh các cấu trúc vòng. Ant không thay thế việc kiểm soát nguồn đầu vào của dự án.

## 7. Kết hợp case sensitivity và followsymlinks

Hai thuộc tính điều khiển hai khía cạnh độc lập:

- **casesensitive** quyết định cách so khớp pattern với tên đường dẫn.
- **followsymlinks** quyết định Ant có đi theo symbolic link trong lúc quét hay không.

Có thể kết hợp chúng trong cùng FileSet:

~~~xml
<fileset dir="assets"
         casesensitive="false"
         followsymlinks="false">
    <include name="**/*.png"/>
    <include name="**/*.jpg"/>
    <exclude name="**/draft/**"/>
</fileset>
~~~

Ý nghĩa:

1. Tìm tệp ảnh có phần mở rộng PNG hoặc JPG không phân biệt hoa thường.
2. Không đi theo symbolic link khi quét.
3. Loại thư mục **draft** ở mọi cấp, không phân biệt cách viết hoa thường.
4. Chỉ các tệp phù hợp với include và không bị exclude mới thuộc tập kết quả.

Ví dụ, **Logo.PNG** có thể được chọn, **draft/old-logo.jpg** bị loại và nội dung nằm sau một symlink không được quét.

Bảng sau tóm tắt các lựa chọn:

| **casesensitive** | **followsymlinks** | Hành vi |
|---|---|---|
| **true** | **true** | Khớp pattern phân biệt hoa thường và đi theo symlink |
| **false** | **true** | Khớp pattern không phân biệt hoa thường và đi theo symlink |
| **true** | **false** | Khớp pattern phân biệt hoa thường, không đi theo symlink |
| **false** | **false** | Khớp pattern không phân biệt hoa thường, không đi theo symlink |

## 8. Áp dụng trong các task Ant

FileSet không tự thực hiện copy hoặc đóng gói. Nó cung cấp tập tài nguyên cho task tiêu thụ nó. Các task phổ biến như **copy**, **delete**, **zip** và **jar** có thể dùng FileSet để giới hạn dữ liệu.

### Copy tài nguyên

~~~xml
<target name="copy-assets">
    <copy todir="build/assets">
        <fileset dir="src/assets"
                 casesensitive="false"
                 followsymlinks="false">
            <include name="**/*.png"/>
            <include name="**/*.svg"/>
            <exclude name="**/draft/**"/>
        </fileset>
    </copy>
</target>
~~~

Task copy chỉ nhận các tài nguyên khớp pattern và không nằm trong thư mục bị loại. Thiết lập không follow symlink giúp tránh lấy thêm nội dung thông qua liên kết ngoài dự kiến.

### Đóng gói ZIP

~~~xml
<target name="archive-docs">
    <zip destfile="build/docs.zip">
        <fileset dir="docs"
                 casesensitive="false"
                 followsymlinks="false">
            <include name="**/*.md"/>
            <include name="**/*.png"/>
            <exclude name="**/draft/**"/>
        </fileset>
    </zip>
</target>
~~~

Ở đây, ZIP chỉ chứa tài liệu Markdown và ảnh PNG được chọn. Việc không theo symlink giữ phạm vi nội dung gắn với cây **docs** được quản lý trực tiếp.

### Đóng gói JAR

~~~xml
<target name="package">
    <jar destfile="build/app.jar">
        <fileset dir="build/classes"
                 casesensitive="true"
                 followsymlinks="false">
            <include name="**/*.class"/>
            <exclude name="**/internal-test/**"/>
        </fileset>
    </jar>
</target>
~~~

Với class đã biên dịch, thường nên giữ quy tắc tên chính xác và không follow symlink nếu không có yêu cầu đặc biệt. Khi cấu trúc package Java phân biệt chữ hoa thường, việc chọn tệp theo tên chính xác giúp tránh vô tình đưa một đường dẫn có cách viết không đúng vào artifact.

## 9. Lưu ý về khác biệt nền tảng và khả năng tái lập

Một build có thể chạy trên Windows của developer nhưng thất bại trên Linux CI vì các nguyên nhân liên quan đến chọn tệp:

- Pattern viết <code>**/*.xml</code> nhưng repository có tệp **Config.XML**.
- Một thư mục symlink tồn tại ở máy cá nhân nhưng không được tạo trong CI.
- Symlink trỏ ra ngoài workspace, nhưng máy CI không có đích đó.
- Hai tệp chỉ khác chữ hoa/thường cùng tồn tại trên filesystem phân biệt hoa thường, nhưng gây xung đột khi checkout hoặc copy sang filesystem không phân biệt hoa thường.
- Các task dùng FileSet khác nhau với thiết lập **casesensitive** hoặc **followsymlinks** không nhất quán.

Để build có thể tái lập:

1. Thống nhất quy ước đặt tên tệp trong repository.
2. Chọn **casesensitive** rõ ràng thay vì dựa vào mặc định khi khác biệt tên có thể ảnh hưởng kết quả.
3. Chọn **followsymlinks** rõ ràng cho các bước copy, archive và publish.
4. Kiểm soát đích symlink và không để build phụ thuộc vào dữ liệu bên ngoài workspace mà CI không quản lý.
5. Dùng include/exclude có mục đích, tránh chọn quá rộng như <code>**/*</code> khi chỉ cần một số loại tệp.
6. Kiểm tra artifact được tạo ra trên môi trường CI để xác nhận tập tệp thực tế.

Lưu ý rằng **casesensitive="false"** chỉ làm pattern matching của Ant không phân biệt hoa thường; nó không sửa tên tệp, không đổi hành vi của filesystem và không giải quyết xung đột tên khi chuyển sang hệ điều hành khác. Tương tự, **followsymlinks="false"** giới hạn việc quét qua liên kết; nó không thay thế việc kiểm tra các tệp được đưa vào build bằng những đường dẫn thông thường.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tệp không được chọn trên Linux nhưng có trên máy developer | Pattern và tên tệp khác chữ hoa thường | Kiểm tra tên thực tế; đặt **casesensitive** theo quy ước mong muốn |
| Tệp **.JPG** bị bỏ qua bởi pattern <code>**/*.jpg</code> | Pattern đang được so khớp phân biệt hoa thường | Dùng **casesensitive="false"** nếu muốn chọn không phân biệt hoa thường |
| Tài nguyên từ thư mục liên kết không được copy | FileSet đặt **followsymlinks="false"** | Nếu thực sự cần nội dung liên kết, bật **true** và kiểm soát đích |
| Artifact chứa dữ liệu ngoài dự án | FileSet theo symlink trỏ ra ngoài thư mục gốc | Giới hạn symlink hoặc tắt follow-link |
| Build trên Windows gặp xung đột tên | Hai đường dẫn chỉ khác chữ hoa thường không thể cùng tồn tại trên filesystem đích | Chuẩn hóa tên trong repository và kiểm tra trước khi copy |
| CI không có cùng tài nguyên như máy cá nhân | Symlink hoặc đích liên kết không được tạo trong workspace CI | Tạo tài nguyên theo cách tái lập hoặc loại liên kết khỏi FileSet |
| Quét thư mục lâu bất thường | Pattern quá rộng hoặc đi theo cây symlink lớn/phức tạp | Thu hẹp include/exclude và xem lại **followsymlinks** |

## 11. Nguyên tắc lựa chọn

Khi cấu hình Ant FileSet, hãy trả lời hai câu hỏi riêng:

- Pattern phải khớp tên tệp có phân biệt chữ hoa thường không? Nếu cần khớp chính xác, dùng **casesensitive="true"**; nếu quy tắc chọn tệp không phụ thuộc cách viết hoa thường, dùng **false**.
- Build có được phép đi theo symbolic link không? Nếu nội dung qua liên kết là một phần có chủ đích của đầu vào, dùng **followsymlinks="true"**; nếu chỉ muốn quét cây thư mục trực tiếp, dùng **false**.

Hai lựa chọn này nên được ghi rõ tại FileSet của task copy, archive hoặc package. Nhờ đó, kết quả build ít phụ thuộc vào cấu hình filesystem của máy chạy và người bảo trì hiểu được chính xác phạm vi dữ liệu Ant sẽ xử lý.

