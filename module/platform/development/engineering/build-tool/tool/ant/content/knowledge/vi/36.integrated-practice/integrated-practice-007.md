# Điều phối hệ thống nhiều dự án với ant hoặc subant

Trong một hệ thống Java có nhiều ứng dụng, thư viện và dịch vụ, từng dự án có thể sở hữu một `build.xml` riêng. Mỗi dự án biên dịch, kiểm thử, đóng gói và quản lý tài nguyên theo yêu cầu của mình; đồng thời nhóm phát triển vẫn muốn có **một lệnh chung** để kiểm tra hoặc tạo bản phân phối toàn hệ thống. Apache Ant cung cấp hai task rất hữu ích cho tình huống này: `<ant>` để gọi **một dự án con**, và `<subant>` để gọi **một nhóm dự án con**.

Điều phối nhiều dự án không chỉ là chạy hàng loạt file XML. Build tổng phải xác định được dự án nào được chọn, thứ tự nào có ý nghĩa, property nào được truyền xuống, lỗi nào phải dừng toàn bộ quy trình và artifact nào được tạo ra. Bài thực hành này đi từ một workspace nhỏ đến hệ thống có phụ thuộc giữa module, kèm cách đọc log và tổ chức lệnh chạy cho CI.

## 1. Tình huống thực tế: nhiều dự án, nhiều buildfile

Giả sử một hệ thống gồm ba module Java:

```text
workspace/
├── build.xml                    # Điều phối cấp hệ thống
├── modules/
│   ├── common/
│   │   ├── build.xml
│   │   └── src/main/java/
│   ├── service/
│   │   ├── build.xml
│   │   └── src/main/java/
│   └── admin/
│       ├── build.xml
│       └── src/main/java/
└── README.md
```

Mục tiêu mong muốn:

- Một lập trình viên có thể chạy riêng `modules/service/build.xml` khi chỉ sửa `service`.
- Pipeline có thể yêu cầu cả ba module chạy target `verify`.
- Có thể lựa chọn chạy `common` trước `service` khi `service` thực sự sử dụng artifact của `common`.
- Nếu một module thất bại, lệnh điều phối trả về lỗi để CI phát hiện.
- Đường dẫn, tham số và log thể hiện rõ dự án nào đang được xử lý.

Không nhất thiết gộp mọi target vào một buildfile rất lớn. Mỗi module có thể giữ cấu hình nội bộ; file `workspace/build.xml` chỉ giữ vai trò điều phối.

## 2. Phân biệt `ant`, `subant` và `antcall`

Ba task này có vẻ gần nhau nhưng không cùng mục đích:

| Task | Tác dụng chính | Khi nào dùng |
| --- | --- | --- |
| `<ant>` | Chạy target trong **một buildfile/dự án Ant khác** | Gọi chính xác một module, kiểm soát thứ tự và tham số từng module |
| `<subant>` | Chạy cùng target qua **nhiều buildfile hoặc nhiều thư mục dự án** | Quét một tập module có giao diện build tương đồng, ví dụ `verify` cho mọi module |
| `<antcall>` | Gọi lại một target trong **cùng buildfile** theo cơ chế gọi Ant mới | Tái sử dụng một target nội bộ khi có lý do riêng; không phải công cụ chính để điều phối nhiều buildfile |

Với `<ant>` và `<subant>`, mỗi lời gọi khởi tạo một ngữ cảnh project Ant con. Điều này khác với việc một target dùng `depends` để chạy các target trong cùng project. Các lời gọi con thông thường sử dụng Ant task bên trong JVM Ant đang chạy; không nên mặc định mỗi `<ant>` tự tạo một tiến trình Java độc lập.

Ví dụ cú pháp:

```xml
<!-- Chạy một dự án con. -->
<ant dir="modules/common"
     antfile="build.xml"
     target="verify"/>
```

```xml
<!-- Chạy target verify trong một nhóm buildfile. -->
<subant target="verify">
    <fileset dir="modules" includes="*/build.xml"/>
</subant>
```

`<subant>` không suy luận được mọi phụ thuộc nghiệp vụ giữa `common`, `service` và `admin` chỉ từ tên thư mục. Nếu một dự án cần artifact do dự án khác tạo, cần mô tả sự phụ thuộc đó và chọn cách điều phối có thứ tự thích hợp.

## 3. Chuẩn bị một giao diện target thống nhất cho từng module

Trước khi dùng `<subant>`, nên thống nhất ý nghĩa những target mà build tổng sẽ gọi. Ví dụ:

| Target tại module | Trách nhiệm |
| --- | --- |
| `clean` | Xóa đầu ra do chính module tạo, trong phạm vi được quản lý |
| `compile` | Biên dịch mã nguồn chính |
| `test` | Chạy kiểm thử mà module đó hỗ trợ |
| `package` | Tạo artifact của module |
| `verify` | Chạy các bước kiểm tra cần thiết cho module |

Không phải mọi module đều phải giống hệt nhau. Module thư viện có thể tạo JAR, module web tạo WAR, module tài nguyên tạo ZIP. Điều quan trọng là **target được build tổng gọi có ý nghĩa đủ thống nhất**. Nếu `<subant target="verify">` được dùng, mỗi module trong tập phải khai báo target `verify`.

Một buildfile tối giản minh họa cho module `common`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="common" default="verify" basedir=".">
    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="dist"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="validate">
        <available file="${src.dir}"
                   type="dir"
                   property="source.exists"/>
        <fail unless="source.exists"
              message="Expected src/main/java in this module"/>
    </target>

    <target name="compile" depends="validate">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/common.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="verify" depends="package">
        <available file="${dist.dir}/common.jar"
                   type="file"
                   property="artifact.exists"/>
        <fail unless="artifact.exists"
              message="common.jar was not created"/>
    </target>
</project>
```

Ví dụ trên có target `verify` xác nhận artifact được tạo. Nó **chưa chạy unit test**; trong một dự án thật, cần bổ sung target `test` và cho `verify` phụ thuộc vào test khi kiểm thử là điều kiện bắt buộc.

Các module `service` và `admin` có thể sử dụng cùng ý tưởng, nhưng cần đổi `project name`, tên JAR và cấu hình mã nguồn/thư viện phù hợp. Trong các ví dụ điều phối bên dưới, giả định cả ba module đã khai báo `verify` và `clean`, và thư mục nguồn cần thiết đã có.

Chạy riêng module `common` để hiểu cách nó hoạt động:

```bash
ant -f modules/common/build.xml verify
```

Lệnh trên giả định terminal đang ở thư mục `workspace`. Ant đọc file `modules/common/build.xml`; vì mỗi buildfile khai báo `basedir="."`, các đường dẫn tương đối trong project con được giải quyết theo base directory mà Ant xác định cho project đó. Để điều phối nhất quán, ví dụ tiếp theo đặt `dir` rõ ràng cho từng lời gọi con.

## 4. Gọi một dự án con bằng `<ant>`

Tạo `workspace/build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="workspace" default="verify-common" basedir=".">
    <target name="verify-common">
        <ant dir="modules/common"
             antfile="build.xml"
             target="verify"
             inheritAll="false"
             inheritRefs="false"/>
    </target>
</project>
```

Gọi:

```bash
ant -f build.xml verify-common
```

Trong lời gọi `<ant>`:

- `dir="modules/common"` chỉ thư mục mà dự án con được chạy.
- `antfile="build.xml"` chỉ file Ant của dự án con, tương đối với `dir` trong ví dụ này.
- `target="verify"` chỉ target mà Ant con sẽ thực thi.
- `inheritAll="false"` giảm việc kế thừa các property thông thường từ project cha.
- `inheritRefs="false"` tránh tự động chuyển các reference từ project cha sang project con.

Nếu không chỉ định `target`, Ant con có thể sử dụng target mặc định của buildfile con. Khi điều phối, việc ghi rõ `target` thường dễ hiểu hơn vì parent cần một hợp đồng cụ thể, ví dụ “mỗi module phải hỗ trợ `verify`”.

### Không nhầm thư mục làm việc với vị trí file build

Một lỗi phổ biến là đặt `antfile` theo đường dẫn từ gốc repository trong khi `dir` cũng đã chỉ tới module:

```xml
<!-- Dễ nhầm phạm vi đường dẫn. -->
<ant dir="modules/common"
     antfile="modules/common/build.xml"
     target="verify"/>
```

Hãy sử dụng cặp `dir="modules/common"` và `antfile="build.xml"` như ví dụ trên để xác định rõ vị trí buildfile của project con. Khi điều tra lỗi, dùng `ant -verbose` để xem các buildfile được đọc và các đường dẫn được giải quyết.

### Một lời gọi Ant con có tác động gì đến build cha?

Ant chạy target được yêu cầu trong ngữ cảnh project con. Các task `<mkdir>`, `<javac>` và `<jar>` trong module vẫn tạo đầu ra trên filesystem chung. Vì thế, ngữ cảnh project khác nhau **không có nghĩa output được cách ly tự động**.

Mỗi module nên tạo đầu ra trong cây của chính nó (`modules/common/build`, `modules/service/build`...). Nếu tất cả cùng ghi vào `workspace/build/classes` mà không phân chia, các task có thể ghi đè hoặc sử dụng nhầm file của module khác.

## 5. Điều phối nhiều dự án theo thứ tự xác định bằng nhiều `<ant>`

Giả sử dịch vụ `service` sử dụng JAR do `common` tạo. Khi đó, build tổng có thể chạy `common` trước, rồi mới chạy `service`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="workspace" default="verify-all" basedir=".">

    <target name="verify-common">
        <ant dir="modules/common"
             antfile="build.xml"
             target="verify"
             inheritAll="false"/>
    </target>

    <target name="verify-service" depends="verify-common">
        <ant dir="modules/service"
             antfile="build.xml"
             target="verify"
             inheritAll="false"/>
    </target>

    <target name="verify-admin" depends="verify-service">
        <ant dir="modules/admin"
             antfile="build.xml"
             target="verify"
             inheritAll="false"/>
    </target>

    <target name="verify-all" depends="verify-admin">
        <echo message="All requested modules completed"/>
    </target>
</project>
```

Thứ tự thực thi có chủ đích:

```text
verify-all
    |
    v
verify-admin
    |
    v
verify-service
    |
    v
verify-common

Thứ tự chạy thực tế:
common → service → admin → verify-all
```

Chạy:

```bash
ant -f build.xml verify-all
```

Ant giải quyết quan hệ `depends` của project cha trước khi gọi target con. Nếu `verify-common` thất bại, `verify-service`, `verify-admin` và `verify-all` thông thường không tiếp tục vì lỗi được truyền lên.

**Điểm quan trọng:** `depends="verify-common"` trong build cha chỉ tạo quan hệ điều phối. Nó không tự động thêm `common.jar` vào classpath của `service`. Module `service` vẫn phải khai báo dependency vào JAR đó hoặc một artifact đã được publish.

Ví dụ trong `modules/service/build.xml` nếu đang sử dụng JAR được tạo tại module khác:

```xml
<path id="compile.classpath">
    <pathelement location="../common/dist/common.jar"/>
</path>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           encoding="UTF-8"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Đoạn trên là phần minh họa cho target của service, không phải file `build.xml` hoàn chỉnh. Đường dẫn `../common/dist/common.jar` được giải quyết từ base directory của module `service`; trong repository thật, nên tách các module bằng artifact repository hoặc đường dẫn đã được khai báo thành property nếu số lượng module lớn.

Một hệ thống nhiều module phát triển lâu dài cần giải quyết phiên bản JAR, dependency transitively và khả năng tái sử dụng artifact. `<ant>` chỉ điều phối công việc; nó không cung cấp cơ chế quản lý dependency artifact hoàn chỉnh như Maven hay Gradle.

## 6. Chạy cùng một target trên nhiều dự án bằng `<subant>`

Khi các module độc lập cùng cung cấp target `verify`, việc lặp ba thẻ `<ant>` có thể được thay bằng một `<subant>`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="workspace" default="verify-modules" basedir=".">
    <target name="verify-modules">
        <subant target="verify"
                inheritAll="false"
                inheritRefs="false"
                failonerror="true">
            <fileset dir="modules"
                     includes="*/build.xml"/>
        </subant>
    </target>
</project>
```

Chạy:

```bash
ant -f build.xml verify-modules
```

Task `subant` lấy những buildfile khớp với `*/build.xml` trong thư mục `modules`, rồi yêu cầu target `verify` ở từng project. Nếu thêm `modules/reporting/build.xml` thỏa điều kiện, module đó cũng được đưa vào tập build mà không phải viết thêm `<ant>`.

Điều kiện quan trọng khi dùng dạng này:

1. Các module được chọn phải có buildfile hợp lệ.
2. Mỗi module phải cung cấp target được yêu cầu (`verify`).
3. Phạm vi FileSet không được vô tình bao gồm buildfile của project cha hoặc thư mục ví dụ không muốn chạy.
4. Không dựa vào thứ tự trả về của `fileset` để đáp ứng dependency giữa các module.
5. Mỗi module tự quản lý đầu ra và bảo đảm các thông số môi trường cần thiết.

`<subant>` phù hợp với những việc “cùng một thao tác, nhiều project”, chẳng hạn kiểm tra cấu hình hoặc chạy test ở các module **độc lập**. Khi một module cần artifact của module khác, phải thiết lập thứ tự phụ thuộc rõ ràng thay vì cho rằng việc liệt kê file build đồng nghĩa đã xác định dependency.

### So sánh hai cách gọi

| Tiêu chí | Nhiều `<ant>` | Một `<subant>` |
| --- | --- | --- |
| Số module | Ít, lựa chọn cố định hoặc cần logic riêng | Nhiều module có giao diện target đồng nhất |
| Kiểm soát thứ tự | Rõ qua thứ tự task hoặc `depends` | Không nên dựa vào FileSet để diễn đạt dependency |
| Cấu hình từng module | Dễ đặt property riêng cho từng lời gọi | Chủ yếu dùng cấu hình chung cho tập module |
| Thêm module | Thường phải thêm lời gọi/target | Có thể tự được chọn bằng mẫu FileSet |
| Dễ phát hiện lỗi module thiếu target | Rõ module nào được gọi | Lỗi xảy ra khi gặp buildfile không có target |
| Phù hợp nhất | Hệ có dependency và bước đặc biệt | Hệ gồm nhiều module tương đương, độc lập |

## 7. Chọn đúng module: tránh quét quá rộng

Ví dụ sau nguy hiểm về mặt phạm vi:

```xml
<subant target="verify">
    <fileset dir="." includes="**/build.xml"/>
</subant>
```

Nó có thể chọn chính buildfile điều phối ở gốc, buildfile mẫu trong tài liệu hoặc một module bị loại khỏi quy trình. Nếu chọn lại buildfile cấp cha, một chuỗi gọi lặp có thể xuất hiện khi cha lại gọi `subant`. Việc này khác với lỗi phụ thuộc vòng tĩnh trong cùng một project và có thể khó phát hiện hơn.

Giới hạn phạm vi:

```xml
<subant target="verify" failonerror="true">
    <fileset dir="modules" includes="*/build.xml">
        <exclude name="sandbox/**"/>
        <exclude name="examples/**"/>
    </fileset>
</subant>
```

Trong cấu trúc ví dụ, `*/build.xml` chỉ nhắm tới buildfile nằm đúng một cấp module bên dưới `modules`. Nếu project có cấu trúc sâu hơn, cần điều chỉnh mẫu theo quy ước repository; không nên tự động mở rộng lên `**/build.xml` khi chưa biết những buildfile khác đang được lưu ở đâu.

Nếu tổ chức module theo danh sách cố định, có thể điều phối bằng các lời gọi `<ant>` riêng theo thứ tự. Với một hệ thống lớn, cần phân biệt **danh sách module thực sự phải build** với “mọi thư mục tình cờ có file build.xml”.

## 8. Truyền cấu hình từ build cha xuống module

Build đa dự án thường chia sẻ một số thông số như phiên bản phát hành, chế độ chạy hoặc đường dẫn kho artifact. `<ant>` hỗ trợ các property lồng bên trong để truyền thông số có chủ đích:

```xml
<target name="package-service">
    <ant dir="modules/service"
         antfile="build.xml"
         target="package"
         inheritAll="false">
        <property name="build.profile" value="ci"/>
        <property name="release.version" value="2.3.0"/>
    </ant>
</target>
```

Trong buildfile con có thể dùng:

```xml
<target name="show-configuration">
    <echo message="Profile: ${build.profile}"/>
    <echo message="Release: ${release.version}"/>
</target>
```

Nếu muốn cho CI quyết định version, có thể khai báo property tại build cha:

```xml
<project name="workspace" default="verify-service" basedir=".">
    <property name="release.version" value="0.0.0-SNAPSHOT"/>

    <target name="verify-service">
        <ant dir="modules/service"
             antfile="build.xml"
             target="verify"
             inheritAll="false">
            <property name="release.version"
                      value="${release.version}"/>
        </ant>
    </target>
</project>
```

Chạy:

```bash
ant -f build.xml -Drelease.version=2.3.0 verify-service
```

Ant dùng cơ chế property thường được đặt một lần. Các property từ dòng lệnh (`-D`) có vai trò đặc biệt và vẫn được truyền tới lời gọi Ant con ngay cả khi `inheritAll="false"`. Vì vậy, `inheritAll="false"` là cách **giảm kế thừa cấu hình không mong muốn**, chứ không phải biện pháp cô lập tuyệt đối khỏi tất cả user property do người chạy cung cấp.

Nếu module nhận đường dẫn xóa/ghi hoặc thông số phát hành, chính module phải kiểm tra giá trị cuối cùng được sử dụng trước khi thực hiện thao tác. Không thể coi một property có giá trị mặc định ở build cha là hằng số bất biến trước tham số dòng lệnh.

### Truyền property chung cho `subant`

`subant` cũng hỗ trợ cấu hình property dùng chung cho các lời gọi con:

```xml
<target name="verify-modules">
    <subant target="verify"
            inheritAll="false"
            failonerror="true">
        <property name="build.profile" value="ci"/>
        <fileset dir="modules" includes="*/build.xml"/>
    </subant>
</target>
```

Mọi module được chọn đều nhận `build.profile` theo cơ chế Ant con. Nếu một module cần cấu hình rất riêng (ví dụ endpoint thử nghiệm khác các module còn lại), thường dễ đọc hơn khi gọi module ấy bằng `<ant>` riêng thay vì cố điều kiện hóa một `subant` chung quá phức tạp.

## 9. `inheritAll` và `inheritRefs`: kế thừa có kiểm soát

Hai thuộc tính này dễ bị nhầm:

| Thuộc tính | Điều khiển | Khi nào nên cân nhắc |
| --- | --- | --- |
| `inheritAll` | Việc kế thừa property thông thường từ parent sang project con | Đặt `false` để giảm việc module vô tình dựa vào property của orchestrator |
| `inheritRefs` | Việc kế thừa các reference được đặt `id` ở parent | Đặt `false` nếu mỗi module tự khai báo path/fileset riêng |

Ant reference có thể là `path`, `fileset` hoặc kiểu dữ liệu khác có `id`:

```xml
<path id="parent.classpath">
    <pathelement location="tools/tool.jar"/>
</path>
```

Nếu module con dựa vào `parent.classpath` nhưng parent không truyền reference này, build con có thể thất bại. Ngược lại, bật kế thừa mọi reference có thể dẫn đến xung đột tên hoặc kết quả khác với chạy module độc lập.

Thiết kế dễ bảo trì thường là **để module con tự chứa đầy đủ cấu hình cần thiết**, rồi chỉ truyền một số property mô tả môi trường hoặc version. Trường hợp thực sự phải chia sẻ reference, cần ghi rõ tên và vai trò, cùng cách hoạt động khi build riêng.

Không nên dùng kế thừa như một cách che giấu việc module thiếu khai báo thư viện. Nếu chỉ build từ cha mới thành công còn chạy module riêng lại thất bại, đó là dấu hiệu module có phụ thuộc ngầm cần giải quyết.

## 10. Xử lý lỗi: thất bại ở module phải được nhìn thấy

Trong CI, mong muốn phổ biến là nếu một module không biên dịch được hoặc test thất bại, toàn bộ job sẽ thất bại. `<ant>` và `<subant>` hỗ trợ `failonerror` để điều khiển việc xử lý lỗi của lời gọi con.

Ví dụ:

```xml
<target name="verify-all">
    <subant target="verify"
            failonerror="true"
            inheritAll="false">
        <fileset dir="modules" includes="*/build.xml"/>
    </subant>
</target>
```

Khi một lời gọi con lỗi, `failonerror="true"` khiến task điều phối báo thất bại và không tiếp tục bình thường. Đây là hành vi mong muốn cho build kiểm tra chất lượng.

Có thể thiết lập `failonerror="false"` khi muốn tiếp tục thử các module khác để thu thập thêm thông tin, nhưng **không nên dùng tùy tiện cho pipeline yêu cầu tất cả module phải thành công**. Nếu lỗi bị bỏ qua và target tổng kết vẫn kết thúc thành công, hệ thống CI có thể báo xanh dù một phần của hệ thống không đạt.

Đặc biệt tránh những mẫu:

```xml
<!-- Dễ che lỗi nếu kết quả tổng được coi là thành công. -->
<subant target="verify" failonerror="false">
    <fileset dir="modules" includes="*/build.xml"/>
</subant>
```

Nếu cần một báo cáo tổng hợp về nhiều lỗi, hãy thiết kế cơ chế thu thập trạng thái và báo lỗi cuối cùng rõ ràng. Bản thân việc chọn `false` không tự tổng hợp thông tin thất bại thành một kết quả chuẩn cho CI.

## 11. Phân biệt lỗi ở build cha và lỗi ở module con

Khi chạy `ant -f build.xml verify-all`, log có thể nhiều tầng:

```text
Buildfile: .../workspace/build.xml

verify-common:
    [ant] Entering .../modules/common/build.xml
    ...

verify-service:
    [ant] Entering .../modules/service/build.xml
    ...
BUILD FAILED
.../modules/service/build.xml:...: ...
```

Đây là log minh họa: cách hiển thị cụ thể phụ thuộc phiên bản Ant, task và chế độ log. Để tìm nguyên nhân, làm theo các bước:

1. Xác định **module đầu tiên thất bại**.
2. Tìm thông báo lỗi thực bên trong buildfile con, trước dòng `BUILD FAILED` tổng hợp.
3. Kiểm tra `dir`, `antfile`, target và property được truyền trong lời gọi parent.
4. Chạy trực tiếp lệnh tương đương ở module con để cô lập lỗi.
5. Sau khi module con chạy được, quay lại lệnh điều phối để kiểm tra thứ tự và cấu hình truyền xuống.

Ví dụ khi `service` thất bại:

```bash
ant -f modules/service/build.xml -verbose verify
```

Nếu trong build cha có truyền property `build.profile=ci`, cần bổ sung tham số tương ứng khi tái hiện độc lập:

```bash
ant -f modules/service/build.xml -Dbuild.profile=ci -verbose verify
```

Trong môi trường nhiều buildfile, các lỗi thường gặp gồm target không tồn tại ở một module, đường dẫn tương đối sai, JAR từ module trước chưa có, classpath thiếu thư viện, property chưa được truyền, hoặc output của module bị module khác ghi đè.

## 12. Target giống tên nhưng khác vai trò: thiết kế “hợp đồng” build con

Một dự án có thể khai báo:

```xml
<target name="verify">
    <echo message="Everything is fine"/>
</target>
```

Mặc dù `<subant target="verify">` chạy thành công, điều đó không có nghĩa module đã biên dịch và kiểm thử. Hợp đồng chung nên mô tả:

- `verify` kiểm tra điều gì: compile, unit test, integration test, kiểm tra static analysis, artifact?
- Điều kiện nào khiến target thất bại?
- Kết quả được ghi ở đâu?
- Module có được phép bỏ qua test hay không, và với tham số nào?
- Có tạo hoặc xóa file nào bên ngoài module không?

Một tập module hỗ trợ `verify` chỉ có giá trị khi nội dung target tương đương ở mức cam kết, không chỉ trùng tên. Điều này đặc biệt quan trọng khi `subant` tự chọn thêm module mới bằng mẫu FileSet.

Có thể đặt thuộc tính `description` cho các target công khai để người dùng xem nhanh bằng `ant -projecthelp`:

```xml
<target name="verify" description="Build and verify this module">
    <!-- compile / test / package theo chính sách module -->
</target>
```

Lệnh `ant -f modules/common/build.xml -projecthelp` giúp hiển thị những target có mô tả. Tuy vậy, danh sách ngắn trong `-projecthelp` không nhất thiết chứa mọi target không có `description`.

## 13. Dọn đầu ra nhiều module bằng `subant`

Giả sử mỗi module có target `clean` xóa **duy nhất** thư mục đầu ra của chính nó. Có thể tạo target dọn toàn hệ thống:

```xml
<target name="clean-modules">
    <subant target="clean"
            inheritAll="false"
            failonerror="true">
        <fileset dir="modules" includes="*/build.xml"/>
    </subant>
</target>
```

Lệnh:

```bash
ant -f build.xml clean-modules
```

Đây là thao tác có ảnh hưởng đến filesystem của nhiều module, vì vậy cần xác nhận tập module chọn chính xác và target `clean` ở từng module có phạm vi an toàn. `subant` chỉ điều phối, không tự kiểm tra target con có xóa quá phạm vi hay không.

**Không nên** cấu hình kiểu:

```xml
<target name="clean-modules">
    <subant target="delete-all">
        <fileset dir="." includes="**/build.xml"/>
    </subant>
</target>
```

Với mẫu rộng, build tổng có thể kích hoạt cả file không dự kiến, đặc biệt nếu một số project có target `delete-all` mang ý nghĩa khác. Thiết kế an toàn hơn là công khai target `clean` có hợp đồng rõ ràng, giới hạn selection và không mặc định đưa thao tác phá hủy vào target build thông thường.

## 14. Áp dụng cho hệ thống có phụ thuộc giữa các module

Xét quan hệ:

```text
common
  |
  v
service
  |
  v
admin
```

Mũi tên ở đây thể hiện artifact đi từ nhà cung cấp sang module sử dụng: `service` cần kết quả `common`, `admin` cần kết quả `service`. Thứ tự build hợp lý là `common → service → admin`.

Với quan hệ này, ba target `<ant>` có thứ tự rõ ràng thường dễ kiểm soát:

```xml
<project name="workspace" default="all" basedir=".">
    <target name="build-common">
        <ant dir="modules/common"
             antfile="build.xml"
             target="package"
             inheritAll="false"/>
    </target>

    <target name="build-service" depends="build-common">
        <ant dir="modules/service"
             antfile="build.xml"
             target="package"
             inheritAll="false"/>
    </target>

    <target name="build-admin" depends="build-service">
        <ant dir="modules/admin"
             antfile="build.xml"
             target="package"
             inheritAll="false"/>
    </target>

    <target name="all" depends="build-admin"/>
</project>
```

Trong dự án thật, thứ tự chỉ là một phần của dependency. Module `service` cần chỉ đúng JAR `common`, phiên bản và vị trí; module `admin` tương tự với `service`. Nếu dự án lớn, kết nối qua kho artifact và khai báo dependency có version sẽ dễ bảo trì hơn cách copy JAR giữa thư mục một cách ngầm định.

Không nên dùng `<subant>` trên danh sách tự phát hiện rồi kỳ vọng tự sắp xếp đúng dependency module. Dù một lần chạy có vẻ đúng thứ tự, nó không thể hiện được quan hệ nghiệp vụ một cách đáng tin cậy.

### Phân nhóm: phần phụ thuộc trước, phần độc lập sau

Một hệ thống có thể có một vài module lõi cần thứ tự rõ, trong khi các module dịch vụ còn lại độc lập:

```text
core-api
   |
   v
core-impl
   |
   +-- feature-a
   +-- feature-b
   +-- feature-c
```

Có thể dùng `<ant>` để tạo lõi, rồi `<subant>` chạy target `verify` cho tập feature sau đó:

```xml
<project name="workspace" default="all" basedir=".">
    <target name="build-core-api">
        <ant dir="modules/core-api" target="package"
             inheritAll="false"/>
    </target>

    <target name="build-core-impl" depends="build-core-api">
        <ant dir="modules/core-impl" target="package"
             inheritAll="false"/>
    </target>

    <target name="verify-features" depends="build-core-impl">
        <subant target="verify"
                inheritAll="false"
                failonerror="true">
            <fileset dir="modules"
                     includes="feature-*/build.xml"/>
        </subant>
    </target>

    <target name="all" depends="verify-features"/>
</project>
```

Ví dụ này mô tả **hai tầng điều phối**: phần lõi dùng thứ tự tường minh, nhóm feature dùng pattern vì mỗi module tuân theo hợp đồng `verify` giống nhau. Muốn một feature được build, bảo đảm nó xuất hiện trong tập FileSet và có dependency đến artifact lõi được khai báo đúng.

## 15. Chạy build tổng trong CI và trên máy phát triển

Các lệnh phổ biến tại gốc repository:

```bash
ant -f build.xml -projecthelp
ant -f build.xml verify-all
ant -f build.xml -Dbuild.profile=ci verify-all
ant -f build.xml -verbose verify-all
```

Phương án CLI nên thống nhất giữa máy phát triển và CI. Với Windows, Linux và macOS, có thể sử dụng cùng `build.xml`, nhưng cần kiểm soát Java/Ant version, file path, executable ngoài, mã hóa và permission. Những bước đó thuộc môi trường chạy, không được `subant` tự chuẩn hóa.

Một pipeline thực tế có thể gồm:

```text
Checkout repository
        |
        v
Thiết lập JDK + Ant
        |
        v
ant -f build.xml verify-all
        |
        +--> module common: compile / test / package
        |
        +--> module service: compile / test / package
        |
        +--> module admin: compile / test / package
        |
        v
Thu thập artifact / báo cáo
```

Nếu module cần credentials hoặc endpoint bên ngoài, CI nên quản lý secret và quyền riêng. Không lưu mật khẩu trong `build.xml` hoặc đưa credential vào log `-verbose`. Bản thân việc gọi chung qua `<ant>` không có nghĩa một module được phép truy cập mọi tài nguyên của module khác.

Điều phối build và điều phối **phát hành** nên được phân biệt. Chạy `verify-all` có thể là hoạt động thường xuyên; target `publish-all` cần yêu cầu xác nhận, version, quyền và kiểm tra đích nhận trước khi thay đổi repository hoặc môi trường đang chạy.

## 16. Cách tạo một bộ phát hành tổng hợp

Sau khi từng module đã tạo artifact, một target cấp cha có thể gom chúng vào một thư mục staging:

```xml
<project name="workspace" default="bundle-all" basedir=".">
    <target name="build-common">
        <ant dir="modules/common" target="package"
             inheritAll="false"/>
    </target>

    <target name="build-service" depends="build-common">
        <ant dir="modules/service" target="package"
             inheritAll="false"/>
    </target>

    <target name="bundle-all" depends="build-service">
        <mkdir dir="build/distribution/lib"/>

        <copy file="modules/common/dist/common.jar"
              todir="build/distribution/lib"/>
        <copy file="modules/service/dist/service.jar"
              todir="build/distribution/lib"/>

        <zip destfile="build/system-distribution.zip"
             basedir="build/distribution"/>
    </target>
</project>
```

Đây là ví dụ tổng hợp cho hai module; cần có `service.jar` được tạo bởi target `package` của `service`. Build cha quản lý `build/distribution`, còn mỗi module tiếp tục quản lý thư mục `dist` riêng. Chạy:

```bash
ant -f build.xml bundle-all
```

Ở hệ thống thật, cần quyết định có xóa staging trước khi gom artifact hay không để tránh ZIP chứa file cũ. Đồng thời phải kiểm tra artifact đầu vào tồn tại, đúng phiên bản và không bị trộn với kết quả của lần build khác. Sự thành công của `<copy>` chỉ khẳng định file được copy theo cấu hình, chưa bảo đảm artifact đúng commit hoặc đã qua kiểm thử.

## 17. Khi nào cần dùng `target` riêng cho từng module?

Một hệ thống có thể vừa có target chung `verify`, vừa có target chuyên biệt:

```xml
<target name="verify-service">
    <ant dir="modules/service" target="integration-test"
         inheritAll="false"/>
</target>

<target name="docs-admin">
    <ant dir="modules/admin" target="generate-docs"
         inheritAll="false"/>
</target>
```

Không có lý do ép tất cả module cung cấp target `integration-test` khi chỉ `service` cần. Trong trường hợp này, `<ant>` làm rõ ý định và tránh làm `<subant>` quá tổng quát.

Ngược lại, một nhóm module đều có thể chạy `lint`, `compile` hoặc `verify` với cùng giao diện là ứng viên phù hợp cho `subant`. Sự kết hợp của hai task thường giúp build tổng vừa cụ thể ở các bước quan trọng, vừa ngắn gọn ở các bước lặp.

## 18. Các lỗi thường gặp khi điều phối nhiều project

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Target "verify" does not exist` | Một module được chọn không khai báo `verify` | Kiểm tra buildfile module và hợp đồng target chung |
| `Basedir ... does not exist` | `dir` sai hoặc module đã di chuyển | Sửa đường dẫn tương đối từ build cha |
| `Buildfile ... does not exist` | Nhầm `antfile` khi đã dùng `dir` | Dùng `dir="modules/x" antfile="build.xml"` |
| Module con chạy riêng được nhưng từ cha lỗi | Property, reference, basedir hoặc môi trường khác | Đối chiếu `inheritAll`/`inheritRefs` và property truyền xuống |
| Service báo thiếu class của common | Chỉ xếp thứ tự build, chưa khai báo classpath/artifact | Thêm dependency vào kết quả của common |
| Hệ thống chạy lặp không dừng | FileSet của `subant` vô tình chọn lại orchestrator | Giới hạn thư mục và mẫu FileSet |
| CI báo thành công dù module lỗi | `failonerror="false"` hoặc task lỗi bị bỏ qua | Đảm bảo lỗi được truyền lên và CI nhận exit code thất bại |
| Bản phân phối chứa JAR cũ | Dùng lại output/staging của lần build trước | Dọn staging được quản lý, kiểm tra artifact nguồn |
| Hai module ghi đè cùng file | Dùng chung thư mục output hoặc cùng tên file đích | Tách output từng module; gom có chủ đích ở parent |
| Module cần thứ tự nhưng dùng FileSet chung | Không mô tả quan hệ module | Dùng `<ant>` và `depends` hoặc mô hình dependency riêng |

Một lỗi hay gặp nữa là lệnh `ant -f build.xml clean verify-all` gây dọn dẹp và build theo thứ tự khác mong muốn khi cấu hình target lồng nhau phức tạp. Hãy đặt tên và phụ thuộc nhất quán, phân biệt `clean-modules` với target build thường, và kiểm tra phạm vi xóa trong mọi buildfile con.

### Mẹo đọc log nhanh

Nếu build tổng thất bại, đừng bắt đầu bằng việc sửa tất cả module. Hãy tìm **module đầu tiên có lỗi thực**, xem task và file được trỏ tới, rồi tái hiện:

```bash
ant -f modules/service/build.xml -verbose verify
```

Sau khi module tự chạy thành công, thử lại từ cha:

```bash
ant -f build.xml -verbose verify-all
```

Sự khác biệt giữa hai lệnh giúp phát hiện lỗi phụ thuộc ngầm vào thứ tự build hoặc property được truyền từ orchestrator.

## 19. Bài thực hành: từ ba module độc lập đến hệ có phụ thuộc

### Phần A — Chạy độc lập từng module

Tạo ba module `common`, `service`, `admin` với `build.xml` riêng. Mỗi module có target `verify` tạo hoặc kiểm tra artifact của chính nó. Chạy từng module để làm rõ giới hạn trách nhiệm:

```bash
ant -f modules/common/build.xml verify
ant -f modules/service/build.xml verify
ant -f modules/admin/build.xml verify
```

Nếu các lệnh đều thành công, mỗi module đã có một lối vào độc lập. Nếu phải chuẩn bị file chỉ có trên một máy để một module chạy được, hãy đưa quy trình chuẩn bị vào build hoặc mô tả dependency rõ ràng.

### Phần B — Điều phối bằng `subant`

Viết target cha:

```xml
<target name="verify-all-independent">
    <subant target="verify"
            inheritAll="false"
            failonerror="true">
        <fileset dir="modules" includes="*/build.xml"/>
    </subant>
</target>
```

Chạy:

```bash
ant -f build.xml verify-all-independent
```

Thử thêm một module có file `build.xml` và target `verify` vào `modules`. Khi mẫu FileSet bao phủ module mới, target cha sẽ chọn thêm module đó. Thử thay tên target trong một module để quan sát Ant phát hiện module thiếu hợp đồng. Sau đó khôi phục target đúng.

### Phần C — Thêm phụ thuộc common → service

Chỉnh `service` để dùng thư viện `common.jar`; khai báo classpath chính xác trong buildfile của `service`. Khi đó, chuyển build tổng thành các lời gọi có thứ tự:

```xml
<target name="verify-common">
    <ant dir="modules/common" target="verify"
         inheritAll="false"/>
</target>
<target name="verify-service" depends="verify-common">
    <ant dir="modules/service" target="verify"
         inheritAll="false"/>
</target>
```

Khi chạy `verify-service` từ build cha, `common` được xử lý trước, còn `service` biết cách dùng artifact của common qua cấu hình dependency trong chính module. Không nên coi việc gọi `subant` qua tất cả module là giải pháp thứ tự khi có phụ thuộc này.

### Phần D — Kiểm soát lỗi và đầu ra

Trong một module thử nghiệm, tạo lỗi biên dịch có thể khôi phục để quan sát build cha thất bại. Sau đó sửa lỗi, chạy lại và xác nhận artifact của từng module được tạo ở đúng thư mục. Khi gom artifact, không chọn file theo mẫu quá rộng từ cả repository.

Với những thao tác dọn dữ liệu hoặc phát hành thật, chỉ thực hiện trên project test và đường dẫn được xác định rõ; việc hiểu cơ chế lỗi không yêu cầu xóa dữ liệu ngoài phạm vi build.

## 20. Thiết kế dễ mở rộng cho nhiều dự án

Khi số module tăng, việc điều phối cần thêm những quy tắc vận hành:

1. **Ranh giới module rõ ràng:** mỗi module quản lý buildfile, nguồn, dependency và output của mình.
2. **Hợp đồng target công khai:** các target như `verify`, `package`, `clean` có ý nghĩa được tài liệu hóa.
3. **Phụ thuộc module tường minh:** những module có quan hệ thứ tự dùng DAG rõ ràng, không dựa vào thứ tự tìm thấy trong thư mục.
4. **Property giới hạn và có kiểm tra:** truyền tham số cần thiết; tránh kế thừa không kiểm soát từ môi trường của developer.
5. **Phạm vi FileSet chính xác:** `subant` chỉ chọn các module được phép điều phối.
6. **Lỗi được truyền về CI:** một module thất bại phải làm kết quả toàn hệ thống thất bại nếu đó là quy tắc pipeline.
7. **Đầu ra phân tách:** artifact module ở một nơi xác định; việc gom distribution được thực hiện ở tầng cha.
8. **Phát hành có kiểm soát:** build/verify thường ngày tách khỏi việc đẩy artifact hoặc deploy môi trường.

Ant có thể điều phối tốt một tập dự án không quá phức tạp bằng `<ant>` và `<subant>`. Nhưng khi quan hệ dependency giữa hàng chục module ngày càng phức tạp, nhu cầu phân giải version, cache và build tăng dần có thể khiến Maven reactor hoặc Gradle multi-project build trở nên phù hợp hơn. Việc lựa chọn công cụ nên dựa vào yêu cầu hệ thống, không phải chỉ vào số lượng file `build.xml`.

## Kết luận

Để điều phối hệ thống nhiều dự án bằng Apache Ant, dùng **`<ant>` khi cần gọi một module cụ thể và kiểm soát rõ thứ tự hoặc tham số**, dùng **`<subant>` khi muốn thực hiện cùng một target trên tập buildfile có hợp đồng thống nhất**. Dù chọn cách nào, từng module vẫn phải tự khai báo dependency và quản lý output; build cha có trách nhiệm chọn module, sắp thứ tự cần thiết, truyền cấu hình có chủ đích và báo lỗi đúng khi một phần của hệ thống thất bại.

Với cấu trúc đó, người phát triển có thể build riêng module để sửa lỗi nhanh, còn CI có một điểm vào chung để kiểm tra hoặc tạo bản phân phối của toàn hệ thống mà không biến buildfile cấp cao thành nơi chứa toàn bộ logic nội bộ của các dự án con.
