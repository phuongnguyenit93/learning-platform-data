# Tổ chức thư mục src, resources, test, build và dist

Một dự án Apache Ant có thể dùng bất kỳ cách sắp xếp thư mục nào, miễn là các đường dẫn trong `build.xml` trỏ đúng tới mã nguồn, tài nguyên và kết quả build. Ant không áp đặt một cấu trúc dự án cố định như một số công cụ build khác. Tuy nhiên, nếu đặt mã nguồn, tài nguyên, mã kiểm thử và sản phẩm build vào các khu vực riêng, người phát triển sẽ dễ hiểu luồng build, dễ tìm lỗi và tránh đưa nhầm tệp trung gian vào gói phát hành.

Trong bài học này, ta tổ chức một dự án Java theo cấu trúc quen thuộc: `src/main` chứa mã và tài nguyên của ứng dụng; `src/test` chứa mã và tài nguyên kiểm thử; `build` chứa kết quả trung gian do Ant tạo ra; `dist` chứa gói bàn giao hoặc phát hành. Đây là quy ước được lựa chọn cho ví dụ, không phải yêu cầu bắt buộc của Ant. Nếu dự án hiện tại dùng tên thư mục khác, có thể giữ nguyên cấu trúc đó và khai báo lại các thuộc tính đường dẫn trong build file.

## 1. Nhìn tổng thể cấu trúc dự án

Một dự án Java nhỏ có thể được tổ chức như sau:

```text
my-ant-project/
├── build.xml
├── README.md
├── .gitignore
├── lib/                         # thư viện JAR bên thứ ba (nếu cần)
├── src/
│   ├── main/
│   │   ├── java/                # mã nguồn ứng dụng
│   │   └── resources/           # tài nguyên dùng khi chạy ứng dụng
│   └── test/
│       ├── java/                # mã nguồn kiểm thử
│       └── resources/           # tài nguyên chỉ dùng khi kiểm thử
├── build/                       # kết quả trung gian do Ant tạo
│   ├── classes/                 # .class và tài nguyên ứng dụng
│   ├── test-classes/            # .class và tài nguyên kiểm thử
│   ├── libs/                    # JAR được build
│   └── distribution/            # thư mục staging trước khi đóng gói
└── dist/                        # gói bàn giao cuối cùng
```

Luồng dữ liệu đi qua các khu vực này:

```text
src/main/java ───────────────┐
                             ├─> build/classes ──> build/libs/*.jar ──┐
src/main/resources ──────────┘                                       │
                                                                     ├─> build/distribution ──> dist/*
src/test/java ───────────────────> build/test-classes                │
src/test/resources ──────────────> build/test-classes                │
```

Mã nguồn và tài nguyên trong `src` là đầu vào do nhóm phát triển quản lý. Các thư mục dưới `build` và `dist` là đầu ra được tạo lại từ đầu vào. Không nên chỉnh sửa thủ công tệp trong `build/classes` hoặc giải nén rồi sửa trực tiếp nội dung trong gói `dist`, vì lần build sau có thể ghi đè những thay đổi đó.

## 2. Thư mục src: nơi lưu mã nguồn

### 2.1. Mã nguồn chính trong src/main/java

`src/main/java` chứa các tệp Java tạo nên chức năng của ứng dụng. Cấu trúc thư mục con thường phản ánh package Java. Ví dụ:

```text
src/main/java/
└── com/
    └── example/
        └── app/
            ├── Main.java
            ├── service/
            │   └── GreetingService.java
            └── model/
                └── Greeting.java
```

Nếu tệp khai báo `package com.example.app.service;`, đường dẫn tương ứng thường là `src/main/java/com/example/app/service/`. Việc giữ package và đường dẫn nhất quán giúp compiler, IDE và các công cụ tìm mã nguồn hoạt động đúng.

Ant dùng task `<javac>` để biên dịch. Thuộc tính `srcdir` chỉ thư mục chứa mã nguồn, còn `destdir` chỉ thư mục nhận các tệp `.class`. Không nên đặt `destdir` trùng với thư mục mã nguồn vì như vậy đầu vào và đầu ra bị trộn lẫn.

### 2.2. Tài nguyên ứng dụng trong src/main/resources

`src/main/resources` chứa các tệp ứng dụng cần đọc khi chạy nhưng không phải mã Java, ví dụ:

- Tệp cấu hình mặc định như `application.properties` hoặc `logging.properties`.
- Tệp mẫu, thông điệp, dữ liệu khởi tạo và nội dung tĩnh.
- Tệp XML, JSON, YAML hoặc các tài nguyên khác được nạp từ classpath.

Ví dụ:

```text
src/main/resources/
├── application.properties
├── messages/
│   └── vi.properties
└── templates/
    └── welcome.html
```

Các tệp này cần được sao chép vào vùng output của ứng dụng. Với cấu trúc đang dùng, ta sao chép chúng vào `build/classes`, cùng nơi chứa bytecode. Khi JAR được tạo từ thư mục này, tài nguyên sẽ nằm trong JAR và có thể được đọc qua classpath.

Ant không tự động sao chép resources chỉ vì thư mục có tên `resources`. Build file phải có task `<copy>` hoặc một cơ chế tương đương. Cần giữ nguyên cấu trúc thư mục tương đối khi sao chép. Ví dụ, `messages/vi.properties` phải tiếp tục nằm dưới `messages/` trong output để đoạn mã truy cập `messages/vi.properties` không bị lỗi.

Không nên đưa mật khẩu, token, khóa riêng hoặc cấu hình bí mật theo môi trường vào resources được đóng gói. Các tệp này có thể được đưa vào JAR và phát hành cho người dùng. Hãy cung cấp cấu hình nhạy cảm từ biến môi trường, secret store hoặc một tệp bên ngoài được quản lý riêng.

## 3. Thư mục test: mã và tài nguyên kiểm thử

Trong cấu trúc ví dụ, kiểm thử được đặt dưới `src/test` để phân biệt rõ với mã ứng dụng:

```text
src/test/
├── java/
│   └── com/example/app/
│       └── GreetingServiceTest.java
└── resources/
    └── sample-data.json
```

`src/test/java` chứa các lớp kiểm thử. `src/test/resources` chứa dữ liệu mẫu, tệp cấu hình hoặc fixture chỉ cần trong quá trình kiểm thử. Những tài nguyên này không nên bị sao chép vào JAR của ứng dụng, trừ khi có một yêu cầu cụ thể.

Mã kiểm thử thường cần truy cập các lớp đã biên dịch của ứng dụng. Vì vậy, classpath khi biên dịch test cần bao gồm `build/classes` và các thư viện kiểm thử. Output của test được đặt riêng ở `build/test-classes`. Việc tách hai output giúp tránh đóng gói lớp kiểm thử vào sản phẩm phát hành.

Ant core có task `<javac>` để biên dịch test, nhưng không tích hợp sẵn một test framework cụ thể. Nếu dùng JUnit, dự án cần khai báo thư viện JUnit và thành phần Ant hỗ trợ JUnit tương ứng. Task `<junit>` là task tùy chọn; cần bảo đảm các JAR cần thiết có trong thư mục thư viện hoặc classpath của Ant. Không nên giả định chỉ cần tạo thư mục `test` là Ant tự tìm và chạy mọi test.

Ví dụ, khi đã chuẩn bị JUnit và Ant JUnit task, classpath kiểm thử có thể gồm:

```xml
<path id="test.classpath">
    <pathelement location="${main.classes.dir}" />
    <pathelement location="${test.classes.dir}" />
    <fileset dir="${lib.dir}" includes="*.jar" />
</path>
```

Phần chạy test sẽ dùng classpath này cùng task `<junit>`. Cấu hình chính xác phụ thuộc phiên bản JUnit và cách dự án cài đặt task tùy chọn. Nếu chưa tích hợp test framework, vẫn nên giữ riêng mã test và output test để có thể bổ sung quy trình kiểm thử sau này.

## 4. Thư mục build: đầu ra trung gian

`build` là khu vực dành cho các tệp được tạo trong quá trình build. Có thể xóa toàn bộ thư mục này và tạo lại từ các tệp nguồn. Cấu trúc con phụ thuộc vào dự án, nhưng cần đặt tên nhất quán để mỗi target biết nơi đọc và ghi.

| Thư mục | Nội dung | Được tạo bởi |
|---|---|---|
| `build/classes` | Bytecode ứng dụng và resources ứng dụng | Target biên dịch và sao chép resources |
| `build/test-classes` | Bytecode test và resources test | Target biên dịch test và sao chép test resources |
| `build/libs` | JAR do dự án tạo ra | Target đóng gói |
| `build/distribution` | Cây thư mục tạm để chuẩn bị gói phát hành | Target staging distribution |

Không phải dự án nào cũng cần tất cả các thư mục này. Ví dụ, một thư viện nhỏ có thể chỉ cần `build/classes` và `build/libs`. Một ứng dụng cần đóng gói nhiều tệp cấu hình, script và thư viện bên ngoài có thể cần thêm thư mục staging.

Nên giữ đầu ra trong một thư mục gốc duy nhất như `build` để target `clean` có thể xóa chúng một cách rõ ràng. Nếu output rải rác vào `src`, thư mục gốc hoặc các vị trí tùy tiện khác, việc dọn dẹp sẽ khó hơn và dễ xóa nhầm tệp do người dùng quản lý.

## 5. Thư mục dist: sản phẩm bàn giao

`dist` (distribution) chứa sản phẩm cuối cùng mà người khác có thể nhận để sử dụng hoặc triển khai. Tùy loại dự án, sản phẩm có thể là:

- Một tệp JAR thực thi hoặc JAR thư viện.
- Một ZIP chứa JAR, README, script khởi chạy và cấu hình mẫu.
- Một gói gồm nhiều thành phần cần được cài đặt cùng nhau.

Ví dụ:

```text
dist/
└── my-ant-project-1.0.0.zip
```

Trong khi `build/libs` lưu JAR được tạo trực tiếp từ bytecode và resources, `dist` lưu gói đã được chuẩn bị cho người nhận. Không phải dự án nào cũng cần hai tầng này: nếu sản phẩm chỉ là một JAR, có thể coi chính JAR là deliverable. Với ví dụ ở bài này, ta giữ JAR trong `build/libs`, sao chép nó vào staging, rồi nén staging thành ZIP trong `dist`.

Thư mục staging giúp xác định chính xác những gì được phát hành. Chỉ sao chép các tệp cần thiết vào staging, ví dụ JAR, hướng dẫn sử dụng và cấu hình mẫu. Tránh sao chép cả thư mục `build` hoặc `src` vào gói phát hành, vì chúng có thể chứa mã nguồn, tệp trung gian, dữ liệu kiểm thử hoặc nội dung không dành cho người dùng cuối.

## 6. Khai báo đường dẫn bằng property trong build.xml

Thay vì lặp lại các đường dẫn ở nhiều target, hãy khai báo chúng thành property ở đầu `build.xml`. Ví dụ:

```xml
<project name="my-ant-project" default="dist" basedir=".">

    <property name="app.name" value="my-ant-project" />
    <property name="app.version" value="1.0.0" />

    <property name="src.main.java" location="${basedir}/src/main/java" />
    <property name="src.main.resources" location="${basedir}/src/main/resources" />
    <property name="src.test.java" location="${basedir}/src/test/java" />
    <property name="src.test.resources" location="${basedir}/src/test/resources" />

    <property name="lib.dir" location="${basedir}/lib" />
    <property name="build.dir" location="${basedir}/build" />
    <property name="main.classes.dir" location="${build.dir}/classes" />
    <property name="test.classes.dir" location="${build.dir}/test-classes" />
    <property name="libs.dir" location="${build.dir}/libs" />
    <property name="dist.stage.dir" location="${build.dir}/distribution" />
    <property name="dist.dir" location="${basedir}/dist" />

    <property name="java.source" value="17" />
    <property name="java.target" value="17" />

</project>
```

`basedir` là thư mục gốc của project Ant. Thuộc tính `location` giúp Ant chuẩn hóa đường dẫn theo môi trường đang chạy. Khi muốn chuyển dự án sang một cấu trúc khác, ta có thể sửa property tương ứng thay vì tìm và thay hàng loạt chuỗi đường dẫn trong các target.

Ví dụ dùng Java 17 ở trên giả định JDK biên dịch hỗ trợ mức source và target đó. Hãy thay giá trị theo phiên bản Java mà dự án thực sự yêu cầu. Với JDK mới, có thể dùng tùy chọn `release` của task `javac` nếu phiên bản Ant đang sử dụng hỗ trợ thuộc tính này; lựa chọn đó kiểm soát API nền tảng tốt hơn việc chỉ đặt `source` và `target`.

## 7. Ví dụ build.xml cho compile, resources, JAR và dist

Sau khi khai báo property, ta định nghĩa các target theo thứ tự phụ thuộc. Mỗi target đảm nhiệm một công việc cụ thể:

1. `prepare` tạo các thư mục output.
2. `process-resources` sao chép tài nguyên ứng dụng.
3. `compile` biên dịch mã nguồn chính.
4. `jar` đóng gói classes và resources thành JAR.
5. `dist` tạo gói ZIP bàn giao.
6. `clean` xóa các kết quả đã sinh.

Ví dụ build file đầy đủ:

```xml
<project name="my-ant-project" default="dist" basedir=".">

    <property name="app.name" value="my-ant-project" />
    <property name="app.version" value="1.0.0" />

    <property name="src.main.java" location="${basedir}/src/main/java" />
    <property name="src.main.resources" location="${basedir}/src/main/resources" />
    <property name="src.test.java" location="${basedir}/src/test/java" />
    <property name="src.test.resources" location="${basedir}/src/test/resources" />

    <property name="build.dir" location="${basedir}/build" />
    <property name="main.classes.dir" location="${build.dir}/classes" />
    <property name="test.classes.dir" location="${build.dir}/test-classes" />
    <property name="libs.dir" location="${build.dir}/libs" />
    <property name="dist.stage.dir" location="${build.dir}/distribution" />
    <property name="dist.dir" location="${basedir}/dist" />

    <property name="java.source" value="17" />
    <property name="java.target" value="17" />

    <property name="jar.file"
              location="${libs.dir}/${app.name}-${app.version}.jar" />
    <property name="dist.file"
              location="${dist.dir}/${app.name}-${app.version}.zip" />

    <target name="prepare">
        <mkdir dir="${main.classes.dir}" />
        <mkdir dir="${test.classes.dir}" />
        <mkdir dir="${libs.dir}" />
    </target>

    <target name="process-resources" depends="prepare">
        <copy todir="${main.classes.dir}">
            <fileset dir="${src.main.resources}" />
        </copy>
    </target>

    <target name="compile" depends="process-resources">
        <javac srcdir="${src.main.java}"
               destdir="${main.classes.dir}"
               encoding="UTF-8"
               source="${java.source}"
               target="${java.target}"
               includeantruntime="false" />
    </target>

    <target name="jar" depends="compile">
        <jar destfile="${jar.file}" basedir="${main.classes.dir}" />
    </target>

    <target name="dist" depends="jar">
        <delete dir="${dist.stage.dir}" />
        <mkdir dir="${dist.stage.dir}" />
        <mkdir dir="${dist.dir}" />

        <copy file="${jar.file}" todir="${dist.stage.dir}" />
        <copy file="${basedir}/README.md"
              todir="${dist.stage.dir}"
              failonerror="false" />

        <zip destfile="${dist.file}" basedir="${dist.stage.dir}" />
    </target>

    <target name="clean">
        <delete dir="${build.dir}" />
        <delete dir="${dist.dir}" />
    </target>

</project>
```

Ví dụ giả định các thư mục nguồn và tài nguyên đã tồn tại, đồng thời dự án có tệp `README.md` ở thư mục gốc nếu muốn đưa tài liệu đó vào gói. Thuộc tính `failonerror="false"` khiến bước sao chép README không làm build thất bại khi tệp hướng dẫn chưa có. Nếu dự án bắt buộc phải phát hành README, hãy bỏ tùy chọn này để thiếu tệp trở thành lỗi rõ ràng.

Target `dist` phụ thuộc vào `jar`, target `jar` phụ thuộc vào `compile`, và `compile` phụ thuộc vào `process-resources`. Ant thực hiện các target phụ thuộc trước target hiện tại. Vì vậy, khi gọi `ant dist`, các bước chuẩn bị, sao chép tài nguyên, biên dịch và đóng gói sẽ diễn ra theo đúng thứ tự.

Trong ví dụ này, JAR chứa nội dung của `build/classes`. Điều đó bao gồm bytecode và resources đã sao chép. Mã kiểm thử không được đưa vào JAR vì `build/test-classes` là một output riêng và không phải thư mục nguồn của task `<jar>`.

## 8. Bổ sung bước biên dịch và chạy test

Khi dự án có test, hãy thêm một luồng output riêng. Target biên dịch test cần phụ thuộc vào việc biên dịch ứng dụng, bởi test thường tham chiếu các lớp chính. Classpath cần có output chính và các JAR kiểm thử.

Ví dụ phần biên dịch test khi dự án lưu thư viện JUnit cùng các dependency test trong `lib`:

```xml
<target name="process-test-resources" depends="prepare">
    <copy todir="${test.classes.dir}">
        <fileset dir="${src.test.resources}" />
    </copy>
</target>

<target name="compile-test"
        depends="compile,process-test-resources">
    <javac srcdir="${src.test.java}"
           destdir="${test.classes.dir}"
           encoding="UTF-8"
           source="${java.source}"
           target="${java.target}"
           includeantruntime="false">
        <classpath>
            <pathelement location="${main.classes.dir}" />
            <fileset dir="${basedir}/lib" includes="*.jar" />
        </classpath>
    </javac>
</target>
```

Đoạn này minh họa cách nối classpath, không tự cung cấp JUnit. Thư mục `lib` phải tồn tại và chứa các JAR mà mã test cần. Nếu dự án quản lý dependency bằng một công cụ khác, hãy lấy các JAR đã resolve từ công cụ đó hoặc cấu hình classpath phù hợp. Không nên chép tùy tiện mọi JAR có trên máy lập trình viên vào build vì điều đó làm kết quả build khó tái lập.

Để thực thi test bằng task `<junit>`, cần cài thành phần Ant JUnit tương thích và thư viện JUnit đúng phiên bản. Sau đó có thể tạo target `test` phụ thuộc vào `compile-test`, cấu hình classpath, formatter và batchtest để tìm các lớp test. Nếu dùng một test runner khác, hãy tích hợp runner đó thành target riêng. Tách riêng `compile-test` và `test` giúp phân biệt lỗi biên dịch test với lỗi khi chạy test.

Không nên cho `build/test-classes` vào classpath đóng gói JAR ứng dụng. Nếu phát hành cả test fixture hoặc test suite là yêu cầu đặc biệt, hãy tạo một artifact riêng với tên và mục đích rõ ràng.

## 9. Chạy build và quan sát kết quả

Từ thư mục gốc có `build.xml`, có thể chạy các lệnh:

```text
ant prepare
ant process-resources
ant compile
ant jar
ant dist
```

Vì target mặc định của ví dụ là `dist`, chỉ cần chạy:

```text
ant
```

Ant sẽ thực hiện target mặc định cùng các dependency của nó. Sau khi build thành công, kiểm tra các đầu ra:

```text
build/
├── classes/
│   ├── com/example/app/*.class
│   └── application.properties
├── libs/
│   └── my-ant-project-1.0.0.jar
└── distribution/
    ├── my-ant-project-1.0.0.jar
    └── README.md

dist/
└── my-ant-project-1.0.0.zip
```

Tên và nội dung thực tế phụ thuộc mã nguồn và resources của dự án. Có thể kiểm tra nội dung JAR bằng công cụ `jar tf` đi kèm JDK hoặc mở ZIP bằng trình quản lý lưu trữ. Hãy xác nhận rằng tài nguyên xuất hiện đúng đường dẫn trong JAR và không có lớp test trong artifact ứng dụng.

Khi muốn build sạch, chạy:

```text
ant clean
ant dist
```

Target `clean` xóa hai khu vực output đã khai báo. Target `dist` tiếp theo sẽ tạo lại chúng. Chỉ nên để `clean` xóa các thư mục build do dự án sở hữu; không đặt đường dẫn của thư mục nguồn, thư mục làm việc cá nhân hoặc thư mục dữ liệu bên ngoài vào target này.

## 10. Quản lý các thư mục sinh tự động bằng Git

Mã nguồn, resources, test, `build.xml` và tài liệu dự án thường cần được quản lý phiên bản. Các thư mục output thường có thể tái tạo nên không cần commit trong quy trình phát triển thông thường.

Một tệp `.gitignore` đơn giản:

```gitignore
/build/
/dist/
```

Quyết định có lưu artifact trong `dist` hay không phụ thuộc quy trình phát hành của nhóm. Nếu cần lưu gói phát hành, nên dùng release repository hoặc kho artifact có version và checksum rõ ràng. Không nên bỏ qua toàn bộ `dist` nếu dự án chủ đích quản lý các gói bàn giao trong Git; khi đó hãy xác định quy tắc cụ thể cho từng loại tệp.

Không đưa `build/classes`, `build/test-classes` hoặc tệp tạm vào Git chỉ để tránh phải chạy build. Những tệp này phụ thuộc môi trường, có thể lỗi thời so với mã nguồn và làm repository tăng dung lượng.

## 11. Các lỗi thường gặp khi tổ chức thư mục

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy thư mục nguồn | Property `srcdir` trỏ sai hoặc cấu trúc thư mục thực tế khác build file | Kiểm tra đường dẫn từ `basedir` và thống nhất tên thư mục |
| Biên dịch thành công nhưng ứng dụng không đọc được tệp cấu hình | Resources chưa được copy hoặc bị đặt sai đường dẫn tương đối | Thêm target copy resources và kiểm tra nội dung JAR |
| JAR chứa cả lớp test | Task đóng gói lấy nhầm thư mục output test | Chỉ dùng `build/classes` làm `basedir` của JAR ứng dụng |
| Test không tìm thấy lớp ứng dụng | Classpath test thiếu `build/classes` | Thêm output chính vào classpath khi biên dịch và chạy test |
| Test không tìm thấy dữ liệu mẫu | Test resources chưa được copy vào `build/test-classes` | Tạo target copy riêng cho `src/test/resources` |
| Gói ZIP có tệp cũ không còn trong dự án | Staging chưa được làm sạch trước khi copy nội dung mới | Xóa và tạo lại thư mục staging trước khi đóng gói |
| Build chạy trên máy này nhưng lỗi trên máy khác | Đường dẫn tuyệt đối, chữ hoa/chữ thường, quyền tệp hoặc dependency khác nhau | Dùng đường dẫn tương đối, chuẩn hóa tên tệp và kiểm tra trên CI |
| Target clean xóa nhầm dữ liệu | Đường dẫn delete quá rộng hoặc property trỏ sai | Chỉ xóa các thư mục output do dự án tạo và kiểm tra property trước khi chạy |

Khi xử lý lỗi, hãy xem log của target đầu tiên thất bại và xác định đường dẫn đầu vào, đầu ra, classpath tại thời điểm đó. Không nên đổi cấu trúc thư mục và sửa mọi target cùng lúc vì sẽ khó nhận ra thay đổi nào đã giải quyết vấn đề.

## 12. Nguyên tắc duy trì cấu trúc lâu dài

- Giữ mã nguồn Java và resources ở các vị trí riêng, đồng thời duy trì đường dẫn package nhất quán.
- Giữ test và test resources tách khỏi đầu vào của artifact ứng dụng.
- Đưa toàn bộ output trung gian vào `build` để có thể dọn sạch và tạo lại.
- Chỉ đưa các tệp cần bàn giao vào staging trước khi tạo `dist`.
- Khai báo đường dẫn bằng property để target dùng chung một nguồn cấu hình.
- Dùng dependency giữa các target để thể hiện thứ tự xử lý thay vì dựa vào thứ tự gọi thủ công.
- Không lưu secret trong resources được đóng gói.
- Ghi nhận dependency và phiên bản công cụ cần thiết để người khác có thể tái tạo build.

Khi dự án lớn dần, có thể bổ sung các thư mục như `reports` cho kết quả kiểm thử, `generated` cho mã nguồn được sinh tự động hoặc `docs` cho tài liệu. Hãy xác định rõ thư mục nào là đầu vào được quản lý và thư mục nào là đầu ra được sinh. Sự phân biệt đó giúp target `clean`, target đóng gói và quy trình CI hoạt động có thể dự đoán được.

