# Tách thư mục đầu ra theo dự án và lần chạy trong Apache Ant

## 1. Vì sao cần tách đầu ra?

Một bản build không chỉ đọc mã nguồn: nó còn tạo file `.class`, JAR, báo cáo kiểm thử, log, file tạm và các sản phẩm trung gian. Nếu nhiều dự án hoặc nhiều lần chạy cùng ghi vào một thư mục như `build/` hay `dist/`, các file này có thể ghi đè lên nhau hoặc bị một tác vụ `clean` xóa nhầm.

Ví dụ, hai job cùng build dự án `alpha` nhưng dùng hai phiên bản mã nguồn khác nhau. Cả hai đều biên dịch vào `build/classes` và đóng gói vào `dist/app.jar`. Job chạy sau có thể xóa class của job trước; kết quả đóng gói có thể chứa file cũ; một job thất bại cũng có thể làm mất log của job còn lại. Tương tự, `alpha` và `beta` có thể vô tình dùng chung `dist/app.jar` nếu đường dẫn đầu ra được viết cố định.

Trong **build tái lập**, yêu cầu đầu tiên là mỗi lần chạy chỉ đọc các đầu vào được chỉ định và chỉ ghi vào vùng đầu ra mà nó sở hữu. Một quy ước hữu ích là:

```text
<output-base>/<project-id>/<run-id>/<loại-sản-phẩm>
```

Với quy ước này:

- **`output-base`**: gốc dành cho toàn bộ sản phẩm được sinh ra, nằm ngoài cây mã nguồn.
- **`project-id`**: định danh ổn định của dự án hoặc module, chẳng hạn `alpha`, `beta`.
- **`run-id`**: định danh của một lần chạy build, chẳng hạn `ci-284-job-1` hay `local-001`.
- **Loại sản phẩm**: `classes/`, `dist/`, `reports/`, `logs/` và các thư mục khác mà build thực sự sử dụng.

Hai lần chạy khác nhau có thể cùng build một dự án; hai dự án có thể dùng cùng `run-id` mà vẫn không va chạm. Tuy nhiên, **hai job ghi đồng thời vào cùng một cặp `(project-id, run-id)` vẫn xung đột**. Vì vậy, `run-id` phải phân biệt các job có thể thực thi song song.

## 2. Quy hoạch cây thư mục

Giả sử repository chứa một file `build.xml` chung và hai dự án Java đơn giản:

```text
repository/
├── build.xml
├── projects/
│   ├── alpha/
│   │   └── src/main/java/demo/App.java
│   └── beta/
│       └── src/main/java/demo/App.java
└── .ant-out/                       # sinh ra trong quá trình build
    ├── alpha/
    │   ├── ci-284-job-1/
    │   │   ├── classes/
    │   │   ├── dist/
    │   │   ├── reports/
    │   │   └── logs/
    │   └── ci-285-job-1/
    │       ├── classes/
    │       ├── dist/
    │       ├── reports/
    │       └── logs/
    └── beta/
        └── ci-284-job-1/
            ├── classes/
            ├── dist/
            ├── reports/
            └── logs/
```

Ở đây, mã nguồn của `alpha` nằm trong `projects/alpha/`; mọi file sinh ra bởi build `alpha` với `run-id=ci-284-job-1` nằm dưới `.ant-out/alpha/ci-284-job-1/`. File của `beta` hoặc lần chạy `ci-285-job-1` không nằm trong phạm vi đó.

Thêm vào `.gitignore` của repository:

```gitignore
.ant-out/
```

Đầu ra là dữ liệu có thể tạo lại; không nên commit nó cùng mã nguồn. Nếu hệ thống CI cần lưu JAR hoặc báo cáo, hãy xuất bản chính xác thư mục sản phẩm của job đó như một artifact sau khi build thành công.

## 3. Cài đặt bằng `build.xml`

Ví dụ sau yêu cầu người gọi cung cấp hai tham số `project.id` và `run.id`. Ant sử dụng chúng để suy ra toàn bộ đường dẫn, kiểm tra định dạng, tạo thư mục và biên dịch/đóng gói một ứng dụng Java đơn giản.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="isolated-ant-build" default="package" basedir=".">

    <!-- Đầu vào chung: repository/projects/<project.id>/... -->
    <property name="projects.base" location="projects"/>

    <!-- Gốc đầu ra; không đặt trong thư mục source của từng dự án. -->
    <property name="output.base" location=".ant-out"/>

    <!-- Tập trung mọi đường dẫn tại một chỗ. -->
    <property name="source.dir"
              location="${projects.base}/${project.id}/src/main/java"/>
    <property name="run.dir"
              location="${output.base}/${project.id}/${run.id}"/>
    <property name="classes.dir" location="${run.dir}/classes"/>
    <property name="dist.dir" location="${run.dir}/dist"/>
    <property name="reports.dir" location="${run.dir}/reports"/>
    <property name="logs.dir" location="${run.dir}/logs"/>

    <!-- Kiểm tra định danh trước khi có thao tác ghi hoặc xóa. -->
    <target name="validate-ids">
        <fail unless="project.id"
              message="Thiếu -Dproject.id=alpha"/>
        <fail unless="run.id"
              message="Thiếu -Drun.id=ci-284-job-1"/>

        <condition property="ids.valid">
            <and>
                <matches string="${project.id}"
                         pattern="^[A-Za-z0-9][A-Za-z0-9_-]*$"/>
                <matches string="${run.id}"
                         pattern="^[A-Za-z0-9][A-Za-z0-9_.-]*$"/>
            </and>
        </condition>
        <fail unless="ids.valid"
              message="project.id/run.id chỉ được chứa chữ, số, _, -; run.id có thể có dấu chấm; phải bắt đầu bằng chữ hoặc số"/>
    </target>

    <target name="validate-source" depends="validate-ids">
        <available file="${source.dir}" type="dir"
                   property="source.exists"/>
        <fail unless="source.exists"
              message="Không tìm thấy thư mục nguồn: ${source.dir}"/>
    </target>

    <!-- Mỗi lần gọi package bắt đầu bằng vùng đầu ra sạch của chính run đó. -->
    <target name="reset-run" depends="validate-source">
        <delete dir="${run.dir}"/>
    </target>

    <target name="prepare" depends="reset-run">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
        <mkdir dir="${reports.dir}"/>
        <mkdir dir="${logs.dir}"/>
        <echo message="Project=${project.id}; Run=${run.id}; Output=${run.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <javac srcdir="${source.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               source="17" target="17"
               encoding="UTF-8"/>
    </target>

    <target name="package" depends="compile">
        <jar destfile="${dist.dir}/${project.id}.jar"
             basedir="${classes.dir}"/>
    </target>

    <!-- Chỉ xóa sản phẩm của một cặp project.id/run.id cụ thể. -->
    <target name="clean-run" depends="validate-ids">
        <delete dir="${run.dir}"/>
    </target>
</project>
```

Để có dữ liệu biên dịch tối thiểu, file `projects/alpha/src/main/java/demo/App.java` có thể chứa:

```java
package demo;

public class App {
    public static void main(String[] args) {
        System.out.println("Hello from alpha");
    }
}
```

Đối với `beta`, tạo file tương ứng và thay thông báo thành `Hello from beta`. Ví dụ dùng cú pháp Java 17; máy thực thi cần JDK và Apache Ant phù hợp. Khi áp dụng vào dự án thực tế, điều chỉnh `source.dir`, cấu hình JDK, classpath và tác vụ đóng gói theo cấu trúc dự án.

### 3.1. Cách Ant tính đường dẫn

`basedir="."` xác định thư mục gốc của project Ant, ở đây là thư mục chứa `build.xml`. Với thuộc tính `location`, Ant chuyển đường dẫn tương đối thành đường dẫn hệ thống dựa trên `basedir`. Như vậy, người dùng gọi Ant từ nhiều vị trí khác nhau vẫn có một mốc thống nhất khi chọn đúng file build.

Các thuộc tính dẫn xuất đều đi từ một công thức:

```text
run.dir = output.base + "/" + project.id + "/" + run.id
```

Tác vụ `<javac>` ghi class vào `${classes.dir}`; `<jar>` lấy class từ đó và ghi file vào `${dist.dir}`. Không có tác vụ nào cần tự ghép lại đường dẫn `build/` hoặc `dist/` ở nơi khác. Khi thêm kiểm thử, báo cáo, tài liệu API hay file sinh từ template, cũng phải cấu hình điểm ghi về những thư mục con tương ứng của `${run.dir}`.

Ant có **property gần như bất biến**: một khi thuộc tính đã có giá trị, lệnh `<property>` thông thường sẽ không ghi đè nó. Thuộc tính truyền bằng `-D` từ dòng lệnh được nạp trước định nghĩa trong `build.xml`. Ví dụ này cố ý không cung cấp giá trị mặc định cho `project.id` và `run.id`, để mỗi lần chạy phải khai báo rõ danh tính trước khi tính đầu ra.

### 3.2. Vì sao cần `validate-ids`?

Nếu ghép trực tiếp dữ liệu tùy ý vào đường dẫn, giá trị như `../other-project` có thể khiến đầu ra thoát khỏi nhánh dự kiến. Mẫu `<matches>` trong ví dụ giới hạn mỗi ID thành một thành phần tên thư mục, không chứa dấu `/` hoặc `\` và không bắt đầu bằng dấu chấm. Nhờ đó, một giá trị ID không thể trực tiếp thêm đường dẫn cha `../` vào công thức.

Điều này bảo vệ đầu vào `project.id` và `run.id`; nó không thay thế việc bảo vệ toàn bộ cấu hình Ant khỏi các tùy chọn không đáng tin cậy. Chẳng hạn, vì property truyền bằng `-D` có quyền ưu tiên, một người có quyền tự ý truyền `-Drun.dir=...` vẫn có thể thay đổi đường dẫn dẫn xuất. Trong pipeline, chỉ cho phép tham số hóa những ID đã kiểm soát, quản lý quyền sửa file build và không dùng `clean-run` với property đường dẫn tùy ý từ nguồn không tin cậy.

`validate-source` tách riêng khỏi `validate-ids` để `clean-run` vẫn có thể dọn một lần chạy cũ khi thư mục source đã được di chuyển hoặc xóa. Trong khi đó, `package` phải xác nhận source tồn tại trước khi xóa vùng đầu ra của chính lần chạy đó.

### 3.3. Vì sao `reset-run` nằm trước `prepare`?

Ant có thể biên dịch tăng dần: nếu chỉ chạy `<javac>` trên thư mục chứa class cũ, một class đã bị xóa khỏi mã nguồn vẫn có thể còn trên đĩa. Jar mới có nguy cơ mang theo class không thuộc phiên bản hiện tại. `reset-run` xóa **duy nhất** `${run.dir}` rồi `prepare` tạo lại các thư mục rỗng trước khi biên dịch. Đây là một lựa chọn ưu tiên tính sạch và dễ tái hiện kết quả hơn tốc độ incremental build.

Nếu muốn dùng incremental build có chủ đích, cần thiết kế cache riêng và định nghĩa rõ khóa cache theo đầu vào. Không nên âm thầm tái sử dụng thư mục kết quả giữa hai run khác nhau.

## 4. Chạy nhiều dự án và nhiều lần build

Từ thư mục `repository/`, chạy:

```bash
# Dự án alpha, lần chạy đầu tiên
ant -f build.xml -Dproject.id=alpha -Drun.id=ci-284-job-1 package

# Dự án beta, cùng mã lần chạy nhưng khác project
ant -f build.xml -Dproject.id=beta -Drun.id=ci-284-job-1 package

# Dự án alpha, một lần chạy khác
ant -f build.xml -Dproject.id=alpha -Drun.id=ci-285-job-1 package
```

Các lệnh trên ghi sản phẩm vào những đường dẫn tách biệt:

| Lệnh build | Thư mục class | File đóng gói |
|---|---|---|
| `alpha`, `ci-284-job-1` | `.ant-out/alpha/ci-284-job-1/classes/` | `.ant-out/alpha/ci-284-job-1/dist/alpha.jar` |
| `beta`, `ci-284-job-1` | `.ant-out/beta/ci-284-job-1/classes/` | `.ant-out/beta/ci-284-job-1/dist/beta.jar` |
| `alpha`, `ci-285-job-1` | `.ant-out/alpha/ci-285-job-1/classes/` | `.ant-out/alpha/ci-285-job-1/dist/alpha.jar` |

Để xóa duy nhất sản phẩm `alpha` của lần chạy `ci-284-job-1`:

```bash
ant -f build.xml -Dproject.id=alpha -Drun.id=ci-284-job-1 clean-run
```

Lệnh này hướng tới `.ant-out/alpha/ci-284-job-1/`; nó không yêu cầu xóa cả `.ant-out/alpha/` hoặc `.ant-out/`. Việc dọn những run cũ hơn theo thời gian lưu giữ nên được quản lý bởi một job bảo trì riêng và tránh các run còn hoạt động.

**Lưu ý về chạy lại:** chạy lệnh `package` lần thứ hai với cùng `(project.id, run.id)` sẽ xóa và tạo lại đầu ra của cặp đó, do `reset-run`. Điều này hữu ích cho thao tác *retry có kiểm soát*, nhưng không an toàn nếu hai job cùng sử dụng cặp ID ấy trong cùng thời điểm. Khi cần lưu đồng thời kết quả của các attempt, đưa attempt vào `run.id`.

## 5. Đặt tên `run-id` trong CI và trên máy cá nhân

`run-id` cần đại diện cho **lần thực thi có thể ghi vào thư mục**. Commit hash là một định danh nguồn tốt nhưng chưa đủ nếu một commit được build nhiều lần hoặc cùng lúc ở các job khác nhau.

| Ngữ cảnh | Ví dụ `run-id` | Lý do |
|---|---|---|
| Build thủ công độc lập | `local-20261113-01` | Người thực hiện tự cấp số để giữ các kết quả riêng |
| Pipeline build | `pipeline-284-job-2` | Phân biệt pipeline và job |
| Chạy lại sau lỗi | `pipeline-284-job-2-attempt-2` | Không ghi đè kết quả attempt trước |
| Ma trận nhiều JDK/hệ điều hành | `pipeline-284-jdk17-linux` | Phân biệt các tổ hợp chạy song song |
| Ma trận có retry | `pipeline-284-jdk17-linux-a2` | Đồng thời phân biệt cấu hình và lần thử |

Hãy lấy định danh từ hệ thống CI (run number, job identifier, attempt, matrix axis) và chuẩn hóa về nhóm ký tự mà `validate-ids` chấp nhận. Không giả định timestamp với độ chính xác tới giây là duy nhất khi nhiều job bắt đầu đồng thời. Nếu tên job chứa dấu cách, `/`, `:` hoặc ký tự ngoài tập cho phép, hãy chuẩn hóa **trước** khi gọi Ant.

Ví dụ, một CI job đã có ID `pipeline-284-job-2-attempt-1` có thể gọi:

```bash
ant -f build.xml \
  -Dproject.id=alpha \
  -Drun.id=pipeline-284-job-2-attempt-1 \
  package
```

Dấu `\` nối dòng trong ví dụ dành cho shell kiểu Unix. Trên Windows PowerShell hoặc Command Prompt, viết cùng lệnh trên một dòng hoặc dùng ký tự nối dòng phù hợp với shell. Các tham số `-Dproject.id=...` và `-Drun.id=...` vẫn là tham số của Ant trên cả hai hệ điều hành.

## 6. Bảo đảm **mọi** file sinh ra đều thuộc đúng run

Tạo `${run.dir}` là chưa đủ nếu một tác vụ khác vẫn ghi file ở vị trí cố định. Khi mở rộng `build.xml`, quy định đầu ra theo từng loại tác vụ:

| Tác vụ / sản phẩm | Cấu hình Ant cần hướng tới thư mục của run |
|---|---|
| Biên dịch Java | `<javac destdir="${classes.dir}" .../>` |
| Đóng gói JAR | `<jar destfile="${dist.dir}/app.jar" .../>` |
| Copy tài nguyên | `<copy todir="${classes.dir}" .../>` hoặc một thư mục phù hợp khác trong `${run.dir}` |
| Báo cáo JUnit | `todir="${reports.dir}"` tại cấu hình formatter/batch test thích hợp |
| Sinh tài liệu Javadoc | `<javadoc destdir="${run.dir}/docs" .../>` |
| File log, báo cáo tùy chỉnh | Khai báo tường minh file đích dưới `${logs.dir}` / `${reports.dir}` |

Một số công cụ được gọi từ Ant có thư mục tạm, cache hoặc mặc định đầu ra riêng. Ví dụ: `exec` gọi script ngoài, compiler plugin ghi file phụ, hoặc test framework sinh báo cáo ở thư mục hiện hành. Cần cấu hình chính những công cụ đó để không làm rò sản phẩm sang `build/`, `target/`, `dist/`, thư mục source hoặc một thư mục tạm dùng chung.

Nếu build gọi build Ant con qua `<ant>` hoặc `<subant>`, phải quyết định rõ cách truyền `project.id`, `run.id` và đường dẫn gốc. Đừng mặc định rằng mọi build con có cùng `basedir` hay mọi property đều nên kế thừa: hãy truyền ID phù hợp cho từng dự án và áp dụng cùng quy ước ở nơi tạo file. Khi gọi hai build con song song, tránh cho chúng cùng sở hữu một `run.dir`.

Đầu ra thực sự cần lưu giữa các lần chạy, như cache dependency, phải có hợp đồng tách biệt: cache đọc/ghi theo khóa đầu vào, kiểm soát đồng thời và có khả năng hủy để build lại. Không sử dụng cache như nơi thay thế artifact chính thức của từng run.

## 7. Tách đầu ra liên quan thế nào đến tính tái lập?

Tách thư mục tạo **tính cô lập**: một lần chạy không dùng nhầm class, JAR hoặc báo cáo của lần chạy khác. Dọn sạch `${run.dir}` trước khi build cũng loại bỏ trạng thái sinh ra từ lượt trước. Đây là nền tảng quan trọng để kiểm soát kết quả, nhưng không đồng nghĩa rằng hai file JAR sẽ luôn có cùng mã băm.

Muốn có build tái lập theo nghĩa *cùng đầu vào tạo ra sản phẩm nhị phân giống nhau*, còn phải kiểm soát nhiều yếu tố:

1. **Nguồn và phụ thuộc:** cùng commit, cùng phiên bản thư viện, không tải dependency kiểu `latest` thay đổi theo thời gian.
2. **Toolchain:** cùng phiên bản Ant, JDK và các công cụ được gọi bên ngoài.
3. **Môi trường:** locale, múi giờ, biến môi trường, thứ tự liệt kê file và các tùy chọn biên dịch có thể ảnh hưởng sản phẩm.
4. **Metadata:** timestamp của entry trong JAR/ZIP, manifest, tên máy, đường dẫn tuyệt đối hoặc thời điểm build có thể khiến sản phẩm khác byte.
5. **Nguồn dữ liệu bổ sung:** tránh phụ thuộc vào file ngẫu nhiên trong workspace, tải mạng không cố định phiên bản hoặc thư mục tạm dùng chung.

Ví dụ, `alpha.jar` ở `ci-284-job-1` và `ci-285-job-1` có thể chứa cùng class về mặt chức năng nhưng khác metadata thời gian của entry. Quy tắc đường dẫn giúp giữ hai sản phẩm riêng để so sánh; muốn so mã băm đáng tin cậy, quy trình đóng gói còn phải chuẩn hóa metadata và các đầu vào khác. Đồng thời, không nên nhúng giá trị `${run.dir}` vốn thay đổi theo từng job vào mã nguồn biên dịch hoặc manifest nếu mục tiêu là artifact byte-for-byte giống nhau.

## 8. Những lỗi thiết kế thường gặp

**Chỉ đổi tên file JAR, vẫn dùng chung `classes/`.** Hai build có thể biên dịch vào một thư mục chung trước khi đóng gói. Cần tách từ đầu ra trung gian đến sản phẩm cuối.

**Tạo thư mục riêng nhưng tác vụ `clean` xóa toàn bộ gốc đầu ra.** Một job đang chạy có thể mất file do job khác gọi `delete dir="${output.base}"`. `clean-run` chỉ xóa `${run.dir}` sau khi ID được kiểm tra.

**Dùng mã commit làm `run-id` duy nhất.** Hai attempt hoặc hai cấu hình matrix của cùng commit vẫn có thể va chạm. Bổ sung run/job/attempt/variant vào định danh.

**Đặt `run-id` mặc định thành một hằng số cho CI.** Mọi job quên truyền ID sẽ dùng chung thư mục. Với build cần cô lập, bắt buộc khai báo như ví dụ sẽ giúp phát hiện cấu hình CI sai sớm.

**Tin rằng Ant tự xóa class cũ.** `<javac>` có thể bỏ qua file mà nó xem là đã cập nhật, và class của source bị xóa không tự biến mất. Xóa phạm vi run trước khi build đầy đủ giúp tránh class mồ côi.

**Cho phép ID chứa `../` hoặc dấu phân cách đường dẫn.** Đầu ra có thể bị chuyển sang nơi ngoài dự kiến; dùng định danh đã chuẩn hóa và kiểm soát cả các property đường dẫn có thể bị override.

**Lẫn lộn output với cache.** Artifact của một run cần có ownership rõ ràng, trong khi cache có thể được tái sử dụng giữa nhiều run theo chính sách riêng. Dùng một thư mục chung cho cả hai dễ làm mất khả năng truy vết.

## 9. Bài thực hành quan sát

Với hai thư mục nguồn `alpha` và `beta`, hãy thực hiện ba lệnh ở mục 4. Quan sát rằng mỗi cặp ID tạo một nhánh `.ant-out/<project-id>/<run-id>/` riêng. Sửa `App.java` của `alpha`, build với một `run-id` mới rồi so sánh thư mục class và JAR của hai lần chạy; file của `beta` không nằm trong vùng ghi của `alpha`.

Tiếp theo, gọi `clean-run` cho `alpha/ci-284-job-1`, sau đó kiểm tra rằng thư mục `alpha/ci-285-job-1` và `beta/ci-284-job-1` vẫn tồn tại. Cuối cùng, thử gọi build mà không có `-Drun.id` hoặc với `-Drun.id=../invalid`: `validate-ids` phải chặn cấu hình trước khi chạy tác vụ xóa hay biên dịch.

Khi chuyển từ ví dụ sang dự án thật, hãy thống nhất một quy tắc: **một job sở hữu đúng một thư mục run, mọi tác vụ ghi vào nhánh đó, và thao tác dọn dẹp chỉ tác động tới phạm vi sở hữu đã được xác thực**. Quy tắc này cho phép build nhiều dự án và nhiều lần chạy đồng thời mà không tự làm bẩn kết quả của nhau, đồng thời tạo cơ sở để kiểm soát các yếu tố tái lập sâu hơn.
