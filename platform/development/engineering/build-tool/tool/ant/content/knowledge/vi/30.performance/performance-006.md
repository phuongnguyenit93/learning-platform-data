# Quản lý cache thư viện và tránh tải lại dependency trong Apache Ant

## 1. Vấn đề hiệu năng: vì sao build Ant thường tải cùng một thư viện nhiều lần?

Trong dự án Java dùng **Apache Ant**, file `build.xml` quy định cách biên dịch, chạy test, đóng gói và triển khai. Ant chủ yếu là công cụ điều phối các **task**; bản thân Ant không có mô hình quản lý dependency Maven/Gradle tích hợp sẵn. Vì vậy, nếu dự án tải thư viện bằng `<get>`, sao chép JAR thủ công hoặc gọi công cụ ngoài, người viết build phải quyết định lúc nào cần truy cập repository và cách tái sử dụng bản đã tải.

Hãy hình dung một dự án cần `commons-lang3-3.14.0.jar`. Khi mọi lần chạy `ant compile` đều tải file từ Internet, tổng thời gian build phụ thuộc vào đường truyền và trạng thái repository, kể cả khi JAR không thay đổi. Trên CI với máy chạy mới mỗi job, việc không lưu cache giữa các job khiến tình trạng lặp lại liên tục.

Mục tiêu của quản lý cache không chỉ là giảm số lần tải. Một thiết kế tốt cần:

- **Tìm thấy thư viện đã tải:** dùng lại artifact đã có với đúng tọa độ và phiên bản.
- **Giải quyết dependency đúng:** biết cả các dependency bắc cầu (transitive) nếu thư viện có khai báo chúng.
- **Phân biệt cache với đầu ra build:** dọn `build/` không đồng nghĩa xóa kho dependency dùng chung.
- **Có quy tắc làm mới:** biết khi nào cần kiểm tra repository hoặc loại bỏ artifact bị lỗi.
- **Hỗ trợ máy phát triển và CI:** cache đặt ở vị trí rõ ràng, có cơ chế lưu/khôi phục và không dựa vào trạng thái máy không được kiểm soát.
- **Giữ tính đúng đắn:** không đánh đổi tính toàn vẹn, phiên bản hoặc tính tái lập của build để lấy tốc độ.

Trong Ant, cách thường gặp là dùng **Apache Ivy** để giải quyết và cache dependency. Nếu dự án nhỏ chỉ có vài JAR và không cần transitive dependencies, `<get>` kết hợp kiểm tra file có thể đủ; hai cách có phạm vi trách nhiệm khác nhau.

## 2. Phân biệt những loại “cache” trong quy trình Ant

Cùng là file JAR nhưng mục đích lưu trữ khác nhau:

| Vị trí hoặc cơ chế | Chứa gì? | Khi nào sử dụng? | Có nên xóa mỗi lần `clean`? |
|---|---|---|---|
| **Ivy dependency cache** | Metadata phân giải dependency và các artifact đã tải | Dùng lại qua nhiều lần resolve, có thể nhiều dự án | Không, nếu là cache dùng chung ngoài thư mục build |
| **Thư mục `build/lib`** | Bản sao JAR được `ivy:retrieve` chuẩn bị cho đóng gói hoặc chạy | Tập hợp file đầu ra của lần build | Có thể xóa và tái tạo từ cache |
| **Thư mục `build/classes`** | File `.class` đã biên dịch | Tránh biên dịch lại khi nguồn không đổi | Có; `clean` thường xóa |
| **Cache của CI** | Bản cache Ivy được đóng gói/lưu giữa những job hoặc lần chạy | Khôi phục môi trường mới nhanh hơn | Theo chính sách khóa cache và lưu trữ CI |
| **Kho dependency nội bộ/repository mirror** | Bản sao artifact được phục vụ qua mạng gần CI | Giảm độ trễ và phụ thuộc Internet công cộng | Quản lý độc lập với `clean` |

**Cache Ivy không phải thư mục đích của `<javac>`.** Ivy giúp lấy đúng JAR; Ant vẫn kiểm soát cách biên dịch và các file sinh ra. Một build có cache dependency đầy đủ vẫn có thể phải biên dịch lại nếu `build/classes` bị xóa.

### 2.1. Tọa độ dependency và file tải về

Một dependency thường được định danh bởi nhóm/tổ chức, tên module, phiên bản và đôi khi là loại artifact hoặc classifier:

```text
organisation : org.apache.commons
module       : commons-lang3
revision     : 3.14.0
artifact     : commons-lang3-3.14.0.jar
```

Ivy phân giải metadata để xác định những artifact cần dùng, sau đó lưu nội dung theo cache của nó. Cache hit nghĩa là **Ivy có thể tái sử dụng artifact sẵn có**; điều đó không đồng nghĩa mọi thao tác kiểm tra metadata hoặc repository đều bị loại bỏ. Với phiên bản động và bản phát hành có thể thay đổi, Ivy còn phải xem chính sách làm mới.

## 3. Dùng Apache Ivy để cache dependency của Ant

**Apache Ivy** là công cụ quản lý dependency có thể tích hợp trực tiếp vào các target Ant. Ivy đọc file mô tả dependency, tìm artifact từ resolver, cache kết quả và cung cấp classpath để Ant dùng.

Vai trò của các thành phần:

```text
ivy.xml
   │ khai báo dependency cần gì
   ▼
ivysettings.xml
   │ chọn repository và vị trí cache
   ▼
<ivy:resolve>
   │ đọc metadata, dùng cache hoặc tải artifact còn thiếu
   ▼
Ivy cache (ví dụ ~/.ivy2/cache)
   ├── metadata / kết quả resolve
   └── các JAR đã tải
           │
           ├── <ivy:cachepath> ──► classpath của <javac>
           └── <ivy:retrieve> ──► build/lib để đóng gói
```

Ivy không nhất thiết được kèm sẵn trong bản cài Ant. Muốn dùng các task `ivy:*`, cần cung cấp **JAR của Ivy** cho Ant, chẳng hạn bằng tùy chọn `-lib` hoặc một cơ chế cài đặt được quản lý tập trung. Nên cố định phiên bản Ivy mà dự án/CI sử dụng.

Một lệnh khởi chạy minh họa:

```bash
# Thay đường dẫn bằng JAR Ivy phiên bản cụ thể đã chuẩn bị trong dự án/CI.
ant -lib tools/ivy-2.x.y.jar compile
```

Ký hiệu `2.x.y` là chỗ giữ chỗ; không phải tên JAR có thể tải trực tiếp. Không nên viết `build.xml` theo cách âm thầm tải một bản Ivy “mới nhất” mỗi lần chạy, vì chính công cụ quản lý dependency cũng sẽ trở thành đầu vào không ổn định.

## 4. Ví dụ hoàn chỉnh: khai báo dependency một lần, tái sử dụng cache khi compile

Giả sử dự án Java có cấu trúc:

```text
ant-ivy-demo/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── tools/
│   └── ivy-<phiên-bản-đã-chọn>.jar
└── src/
    └── org/example/App.java
```

Thư mục `build/` được tạo trong quá trình build. File `ivy.xml` và `ivysettings.xml` là cấu hình nguồn, nên được kiểm soát phiên bản cùng mã nguồn.

### 4.1. File `ivy.xml`: khai báo phiên bản thư viện cố định

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info organisation="org.example"
          module="ant-ivy-demo"
          revision="1.0"/>

    <configurations>
        <conf name="compile" visibility="public"/>
    </configurations>

    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0"
                    conf="compile->default"/>
    </dependencies>
</ivy-module>
```

Ở đây:

- `organisation` và `module` trong `<info>` định danh **module hiện tại**.
- `<conf name="compile">` khai báo tập dependency cần cho quá trình biên dịch.
- `org`, `name`, `rev` trong `<dependency>` chỉ định thư viện cần lấy.
- `conf="compile->default"` ánh xạ cấu hình `compile` của dự án sang cấu hình `default` của thư viện.
- `rev="3.14.0"` ghim một phiên bản cụ thể, tránh phải giải quyết “bản mới nhất” theo kết quả thay đổi từng ngày.

Ivy có thể đọc thông tin dependency bắc cầu từ metadata phù hợp của artifact, chẳng hạn POM ở repository Maven. Đây là lý do Ivy thuận tiện hơn việc liệt kê các URL JAR thủ công.

### 4.2. File `ivysettings.xml`: cấu hình resolver và cache

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivysettings>
    <settings defaultResolver="central"/>

    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 usepoms="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>

    <caches defaultCacheDir="${ivy.default.ivy.user.dir}/cache"/>
</ivysettings>
```

`<ibiblio>` là resolver của Ivy hỗ trợ cách tổ chức repository tương thích Maven. `usepoms="true"` giúp Ivy sử dụng metadata POM khi có để phân giải quan hệ dependency.

Giá trị `ivy.default.ivy.user.dir` mặc định thường tương ứng thư mục `.ivy2` trong home của người chạy. Vì vậy, một đường dẫn cache quen thuộc là:

```text
Linux/macOS:  ~/.ivy2/cache
Windows:      %USERPROFILE%\.ivy2\cache
```

Đây là **cache trên máy đang chạy**; nếu CI tạo một môi trường hoàn toàn mới thì cache này không tự đi theo job tiếp theo. Phần sau sẽ trình bày cách lưu và khôi phục cache trong CI.

Có thể chuyển repository sang một máy chủ nội bộ bằng cách cấu hình resolver tương ứng. Nếu dự án chỉ cho phép dùng mirror của doanh nghiệp, không nên giữ một nhánh dự phòng âm thầm truy cập Internet công cộng mà chưa được chấp thuận.

### 4.3. File `build.xml`: resolve một lần, dùng classpath trực tiếp

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-ivy-demo"
         default="compile"
         basedir="."
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="src.dir" location="src"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.lib.dir" location="${build.dir}/lib"/>

    <target name="resolve">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:resolve file="ivy.xml" conf="compile"/>

        <!-- Tham chiếu trực tiếp đến những artifact Ivy đã cache. -->
        <ivy:cachepath pathid="dependencies.compile"
                       conf="compile"/>
    </target>

    <target name="compile" depends="resolve">
        <mkdir dir="${classes.dir}"/>

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="dependencies.compile"/>
        </javac>
    </target>

    <!-- Chỉ lấy bản sao JAR khi cần đóng gói hoặc phân phối. -->
    <target name="stage-libs" depends="resolve">
        <mkdir dir="${dist.lib.dir}"/>

        <ivy:retrieve conf="compile"
                      pattern="${dist.lib.dir}/[organisation]/[module]/[artifact]-[revision].[ext]"
                      sync="true"/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

</project>
```

Các điểm chính:

1. `resolve` chạy `<ivy:resolve>` trước khi tạo path. Artifact đã có và còn hợp lệ sẽ được sử dụng từ cache; artifact thiếu có thể được tải.
2. `<ivy:cachepath>` biến danh sách artifact trong cache thành một **Ant path**. `<javac>` tham chiếu path đó trực tiếp nên không phải sao chép JAR sang `build/lib` mỗi khi chỉ cần compile.
3. `stage-libs` chỉ dùng khi thực sự cần một thư mục chứa JAR cho bước đóng gói/chạy. `<ivy:retrieve>` là thao tác sao chép từ kết quả Ivy đã phân giải; nó không nhất thiết tải lại từ Internet.
4. Mẫu `[organisation]/[module]/...` giữ thư viện trong các thư mục riêng, hạn chế đụng tên giữa những module khác nhau. Nếu dùng classifier hoặc nhiều artifact cùng tên, thiết kế pattern đầy đủ theo tập artifact thực tế.
5. `sync="true"` giúp loại bỏ các file đã retrieve cũ không còn nằm trong tập cần lấy. **Chỉ dùng khi thư mục đích là staging do riêng task này sở hữu**, vì cơ chế đồng bộ có thể xóa file không còn khớp.
6. `clean` chỉ xóa `build/`. Cache Ivy ở home người dùng được giữ lại, nên lần compile kế tiếp vẫn có thể sử dụng JAR đã tải.

Trong **cùng một lần gọi Ant**, target `resolve` là dependency chung và không cần bị thực thi nhiều lần chỉ vì cả `compile` và `stage-libs` đều phụ thuộc vào nó. Tuy nhiên, khi chạy hai lệnh Ant độc lập, mỗi lệnh vẫn có thể thực hiện lại bước kiểm tra resolve; cache giúp hạn chế việc tải dữ liệu artifact lần nữa.

### 4.4. Chạy lần đầu và những lần tiếp theo

```bash
# Lần đầu: Ivy có thể cần lấy metadata và JAR từ repository.
ant -lib tools/ivy-2.x.y.jar compile

# Lần sau: dùng lại nội dung cache khi có thể.
ant -lib tools/ivy-2.x.y.jar clean compile

# Chỉ chuẩn bị thư viện trong thư mục staging khi cần.
ant -lib tools/ivy-2.x.y.jar stage-libs
```

Ở lần đầu, cache **lạnh (cold cache)**; các artifact cần dùng có thể phải tải. Ở lần kế tiếp, cache **ấm (warm cache)**; những artifact có sẵn thường không phải tải lại. Dù vậy, Ivy có thể vẫn phải kiểm tra trạng thái metadata hoặc repository theo cấu hình và loại revision.

Điểm cần nhớ là `ant clean compile` xóa output compile nhưng vẫn giữ cache bên ngoài `build/`. Nếu đặt Ivy cache ngay trong `build/` rồi dùng `clean` xóa toàn bộ `build/`, dự án sẽ tự làm mất lợi ích cache mỗi lần clean.

## 5. Khóa phiên bản để cache có ý nghĩa và build ổn định

Một cache nhanh nhưng luôn cung cấp nội dung không xác định là thiết kế nguy hiểm. Cần phân biệt:

| Cách khai báo revision | Hành vi | Tác động đến cache/build |
|---|---|---|
| `3.14.0` | Yêu cầu phiên bản cố định | Dễ chia sẻ cache và so sánh kết quả hơn |
| `latest.release`, `latest.integration` | Ivy chọn phiên bản theo trạng thái repository | Có thể phải tra cứu metadata thường xuyên; đầu ra thay đổi khi có bản mới |
| Revision khoảng hoặc mẫu động | Tập phiên bản phù hợp có thể tăng theo thời gian | Cần kiểm tra cập nhật; giảm khả năng lặp lại cùng đầu vào |
| `*-SNAPSHOT` / artifact được thay thế tại cùng revision | Nội dung của “cùng phiên bản” có thể đổi | Phải có chính sách kiểm tra/làm mới riêng; dễ gặp cache cũ |

**Ưu tiên dependency phiên bản cụ thể và artifact không bị thay thế sau phát hành.** Đây là cách giảm cả số lần truy vấn repository và rủi ro hai build lấy hai byte khác nhau dưới cùng một tên phiên bản.

Nếu cần cập nhật một thư viện, sửa `ivy.xml` có chủ đích, phân giải lại, kiểm tra tác động rồi ghi nhận thay đổi. Không nên coi việc xóa toàn bộ cache trước mỗi build là cách “đảm bảo luôn mới”; cách đó làm build chậm và không bảo đảm các phiên bản động sẽ cho kết quả tái lập.

### 5.1. Dependency bắc cầu có thể thay đổi tập JAR

Ví dụ thư viện A cần B và C. Chỉ cache A là chưa đủ; Ivy cần giải quyết cả graph dependency. Nếu có thay đổi metadata hoặc quy tắc xung đột phiên bản, tập JAR có thể khác dù dependency trực tiếp vẫn như cũ.

Với yêu cầu tái lập nghiêm ngặt, cần quản lý toàn bộ graph đã giải quyết, repository đáng tin cậy và chính sách kiểm soát phiên bản, thay vì chỉ ghim một vài dependency trực tiếp.

### 5.2. Cache không phải cơ chế xác thực nguồn gốc

Một JAR hiện diện trong cache không tự chứng minh nó an toàn hoặc đúng với artifact dự kiến. Khi xây dựng chính sách dependency, cần quan tâm:

- Repository tin cậy và kết nối HTTPS.
- Checksum/chữ ký hoặc cơ chế xác minh artifact phù hợp.
- Quy định về artifact bất biến, thay vì ghi đè cùng revision.
- Tránh chia sẻ cache có khả năng bị ghi vào bởi các job không tin cậy.
- Tách cache hoặc chính sách truy cập nếu các môi trường có mức độ tin cậy khác nhau.

Ivy hỗ trợ các cơ chế kiểm tra checksum; hiệu lực phụ thuộc cấu hình resolver, repository và cách người dùng xử lý lỗi. Không nên bỏ qua kiểm tra tính toàn vẹn chỉ để giảm thời gian build.

## 6. Trường hợp không dùng Ivy: dùng `<get>` nhưng phải có chính sách cache

Một số dự án Ant chỉ cần một JAR đơn giản và đã biết chính xác URL. Ant có task `<get>` để tải tài nguyên từ URL về file đích.

Ví dụ:

```xml
<project name="manual-library-download" default="prepare-libs">
    <property name="lib.dir" location="lib-cache"/>

    <target name="prepare-libs">
        <mkdir dir="${lib.dir}"/>

        <get src="https://repo.maven.apache.org/maven2/org/apache/commons/commons-lang3/3.14.0/commons-lang3-3.14.0.jar"
             dest="${lib.dir}/commons-lang3-3.14.0.jar"
             skipexisting="true"
             usetimestamp="false"/>
    </target>
</project>
```

Với `skipexisting="true"`, nếu file đích đã tồn tại, Ant bỏ qua việc tải lại. Cách làm phù hợp với artifact bất biến **khi đã có quy trình xác minh file được cache**.

Giới hạn quan trọng:

- `<get>` **không tự giải quyết dependency bắc cầu** từ metadata POM.
- Kiểm tra “file đã tồn tại” không xác nhận file còn nguyên vẹn hay đúng checksum.
- Nếu người dùng thay file trong cache bằng một JAR khác cùng tên, `skipexisting` có thể giữ lại bản sai.
- Tự quản lý nhiều URL sẽ phức tạp khi hệ thống có hàng chục thư viện và nhiều phiên bản.

Thuộc tính `usetimestamp="true"` cho phép `<get>` dùng thông tin thời gian sửa đổi để thực hiện tải có điều kiện khi máy chủ hỗ trợ; nó **không phải bằng chứng rằng nội dung đúng hoặc artifact không thay đổi**. Không nên thay cơ chế pin phiên bản và kiểm tra checksum bằng timestamp.

Nếu cần dependency bắc cầu, quản lý version conflict hoặc nhiều cấu hình runtime/test, Ivy thường phù hợp hơn tập hợp `<get>` rời rạc.

## 7. Cache trong CI: giữ artifact giữa các lần chạy

Trên máy lập trình viên, home directory thường tồn tại lâu dài, vì vậy `~/.ivy2/cache` tự nhiên được tái sử dụng. Trong CI, mỗi job có thể chạy trên môi trường trống, khiến cache phải được khôi phục từ storage của hệ thống CI.

### 7.1. Nguyên tắc cache key

Một cache key thường phụ thuộc vào:

- Hệ điều hành hoặc nền tảng khi các artifact có thể khác nhau theo nền tảng.
- Phiên bản toolchain cần phân biệt, ví dụ JDK và Ivy.
- Nội dung khai báo dependency và cấu hình resolver (`ivy.xml`, `ivysettings.xml`).
- Những file ảnh hưởng đến graph dependency của dự án, nếu có.

Ví dụ khóa logic:

```text
ivy-linux-jdk17-ivy2.5-<hash(ivy.xml, ivysettings.xml)>
```

Khi file khai báo dependency đổi, hash đổi và CI có thể lưu một phiên bản cache mới. Một cơ chế **restore theo tiền tố** giúp tận dụng dữ liệu chung của cache cũ, nhưng quá trình resolve vẫn phải đối chiếu dependency hiện tại. Không được coi cache khôi phục là danh sách dependency đã được khóa sẵn.

### 7.2. Ví dụ GitHub Actions

Một workflow minh họa dùng `actions/cache` để lưu thư mục Ivy:

```yaml
name: Build with Ant

on:
  push:
  pull_request:

jobs:
  compile:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: actions/cache@v4
        with:
          path: ~/.ivy2/cache
          key: ivy-${{ runner.os }}-jdk17-${{ hashFiles('ivy.xml', 'ivysettings.xml') }}
          restore-keys: |
            ivy-${{ runner.os }}-jdk17-

      - name: Compile
        run: ant -lib tools/ivy-2.x.y.jar clean compile
```

**Trước khi chạy thật**, thay `tools/ivy-2.x.y.jar` bằng đường dẫn đến một phiên bản Ivy cụ thể đã được chuẩn bị. Ví dụ trên giả định job đã có Ant và JAR Ivy ở vị trí ấy; nếu chưa có, bước cài/chuẩn bị công cụ phải được khai báo riêng trong workflow.

Chuỗi hoạt động:

1. Checkout mã nguồn và cài JDK.
2. CI thử khôi phục cache `~/.ivy2/cache` dựa trên key.
3. Ant/Ivy resolve dependencies, tái sử dụng file có sẵn; chỉ lấy thêm những artifact cần thiết.
4. Sau job, cơ chế cache của CI có thể lưu lại dữ liệu theo chính sách của nền tảng.

Các bước cache không thay thế dependency resolution. Đừng phụ thuộc vào một cache archive để làm nguồn chân lý duy nhất về nội dung dependency. Cần chú ý chính sách cache cho pull request từ nguồn không tin cậy và cách CI cấp quyền ghi/khôi phục để tránh cache bị đầu độc.

### 7.3. Cache Ivy hay cache cả `build/`?

Hai lựa chọn phục vụ mục đích khác nhau:

- **Cache Ivy**: tập trung vào tải dependency, tương đối ổn định khi nhiều nhánh hoặc lần build dùng cùng thư viện.
- **Cache `build/classes`**: tập trung vào biên dịch gia tăng; muốn an toàn phải nhận diện chính xác những thay đổi mã nguồn, compiler, options và các input khác.

Với bài toán **tránh tải lại dependency**, ưu tiên cache Ivy trước. Cache toàn bộ thư mục build khi chưa có cơ chế xác định độ mới có thể vô tình sử dụng class file lỗi thời hoặc output của nhánh khác.

## 8. Chạy offline: cache đủ chưa?

Có hai trạng thái cần phân biệt:

1. **Cache đủ dữ liệu:** phần lớn JAR đã có trên máy nên Ivy có thể không cần tải lại payload.
2. **Build offline có cam kết:** build không được phép truy cập mạng và sẽ thất bại có thông báo khi thiếu input.

Hai trạng thái không đồng nghĩa. Với cấu hình resolver trỏ tới repository từ xa, Ivy vẫn có thể liên hệ repository để kiểm tra metadata hoặc phiên bản động, ngay cả khi đã có nhiều artifact trong cache. Không nên tự tuyên bố một build là offline chỉ vì đã chạy thành công ở lần thứ hai.

Nếu cần môi trường **cách ly hoàn toàn khỏi mạng**, có thể chuẩn bị một bộ JAR đầy đủ từ trước rồi cho Ant biên dịch trực tiếp từ thư mục đã được xác minh. Ví dụ:

```text
offline-package/
├── build.xml
├── src/
│   └── org/example/App.java
└── vendor/
    └── lib/
        └── commons-lang3-3.14.0.jar
```

`build.xml` dành cho bản offline tối giản:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="offline-compile" default="compile-offline">

    <property name="source.dir" location="src"/>
    <property name="vendor.dir" location="vendor/lib"/>
    <property name="classes.dir" location="build/classes"/>

    <target name="compile-offline">
        <available file="${vendor.dir}/commons-lang3-3.14.0.jar"
                   property="commons.lang3.present"/>

        <fail unless="commons.lang3.present"
              message="Thiếu JAR commons-lang3 trong vendor/lib"/>

        <mkdir dir="${classes.dir}"/>

        <javac srcdir="${source.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath>
                <fileset dir="${vendor.dir}" includes="**/*.jar"/>
            </classpath>
        </javac>
    </target>

</project>
```

Không có `<get>` hoặc `<ivy:resolve>` trong target này nên target tự nó không yêu cầu tải dependency. Với dự án thực tế, phải chuẩn bị **đủ mọi dependency bắc cầu**, kiểm tra checksum của bộ JAR và đảm bảo các task biên dịch/xử lý khác cũng không âm thầm gọi mạng.

Cách khác là cấu hình Ivy dùng repository nội bộ có thể truy cập trong vùng mạng riêng hoặc resolver chỉ đọc dữ liệu cục bộ. Việc này cần cấu hình repository và cơ chế metadata phù hợp; chỉ đổi một Ant property tên `offline` không tự biến resolver từ xa thành offline.

## 9. Vận hành cache: làm mới, dọn dẹp và khắc phục lỗi

### 9.1. Khi nào nên xóa cache?

Đừng xóa toàn bộ cache trước mỗi lần build. Chỉ cần xem xét làm sạch khi có bằng chứng cụ thể, chẳng hạn artifact bị hỏng, metadata cache không còn tương thích với cấu hình repository hoặc đang điều tra sai khác giữa máy.

Nếu cache Ivy nằm trong home và được chia sẻ cho nhiều dự án, thao tác xóa toàn bộ thư mục có thể khiến **tất cả dự án trên máy** phải tải lại thư viện. Ưu tiên điều tra đúng artifact hoặc dùng một cache riêng biệt để thử nghiệm trước khi tác động đến cache dùng chung.

Cần phân biệt hai hành động:

```text
ant clean
    → xóa build/classes, build/lib và output do build sở hữu

xóa/cache invalidation của Ivy
    → thay đổi dữ liệu dependency đã tải, có thể ảnh hưởng nhiều build
```

Hai thao tác không nên bị gộp vào một target `clean` thông thường.

### 9.2. Khi nào phải resolve lại?

Tập artifact cần dùng có thể thay đổi khi:

- `ivy.xml` thêm, bỏ hoặc nâng phiên bản một dependency.
- `ivysettings.xml` thay repository, cấu hình resolver hoặc cách giải quyết metadata.
- Một dependency bắc cầu xuất hiện hoặc thay đổi do metadata được cập nhật.
- Dùng revision động hoặc artifact mà nội dung có thể đổi dưới cùng revision.
- Cache bị thiếu, lỗi hoặc bị dọn theo thời hạn lưu trữ.

Sau thay đổi dependency, phải để Ivy resolve theo cấu hình mới. Không nên chỉ dùng lại `build/lib` cũ mà bỏ qua bước resolve vì có thể chứa phiên bản không còn được yêu cầu.

### 9.3. Những nguyên nhân vẫn khiến build chậm dù đã có cache

| Hiện tượng | Khả năng cần xem xét | Hướng giải quyết |
|---|---|---|
| Mỗi build tải lại cùng JAR | Cache nằm trong thư mục bị `clean` xóa, hoặc mỗi job CI có home mới | Đặt cache ngoài `build/`; cache/restore trên CI |
| Không tải JAR nhưng resolve vẫn chậm | Kiểm tra metadata, revision động, repository xa hoặc lỗi kết nối | Ghim revision, xem resolver và log truy cập mạng |
| Một build gọi resolve nhiều lần | Target trùng lặp, chạy nhiều lời gọi Ant độc lập hoặc subproject tự resolve | Gom dependency resolution hợp lý; tái sử dụng path trong một invocation |
| Compile vẫn chậm | Mất `build/classes` hoặc thay đổi nguồn/task options | Phân tích thời gian compile riêng; không coi đây là lỗi cache dependency |
| `build/lib` có JAR cũ | Retrieve không đồng bộ staging hoặc pattern chồng lấn | Dành riêng staging và cân nhắc `sync="true"` |
| Cache hit nhưng test lỗi trên CI | JDK/OS khác, xung đột dependency, thiếu artifact hoặc file cache không hợp lệ | Cố định toolchain; kiểm tra graph và artifact |
| Cache CI quá lớn | Nhiều phiên bản/nhánh tích lũy hoặc policy lưu quá rộng | Dùng key và vòng đời cache phù hợp; dọn định kỳ có kiểm soát |

Các dòng log Ivy cho biết phần nào đang resolve, metadata/artifact nào được lấy hoặc lấy lại từ cache. Nên đọc log của **lần chạy cache lạnh** và **lần chạy cache ấm** để xác định phần nào thực sự đã giảm chi phí.

## 10. Đo lợi ích cache đúng cách

Không nên kết luận “cache nhanh hơn” chỉ bằng một lần quan sát ngẫu nhiên. Thời gian chạy còn phụ thuộc tốc độ mạng, tải CPU, số file source và độ trễ repository.

Một phép đo đơn giản gồm:

1. Chạy với cache riêng chưa có artifact để quan sát **cold cache**.
2. Giữ nguyên cùng bộ input, chạy lại để quan sát **warm cache**.
3. Tách thời gian `resolve` và `compile` nếu muốn tìm nút thắt.
4. So sánh số artifact thực sự phải tải trong log, thay vì chỉ so sánh tổng thời gian.
5. Trên CI, so sánh job có cache khôi phục với job không có cache, nhưng cùng runner/toolchain và graph dependency.

Ví dụ chạy Ant với log chi tiết:

```bash
ant -lib tools/ivy-2.x.y.jar -verbose compile
```

Log `-verbose` có thể rất dài; chỉ bật khi điều tra. Với cache tốt, lần chạy sau thường giảm phần tải artifact, nhưng compile có thể vẫn tốn thời gian vì `clean` đã xóa `.class`. Tốc độ cuối cùng phụ thuộc quy mô thư viện, kết nối mạng và mức độ hiệu quả của cache.

### 10.1. Vì sao phải quan sát cả độ đúng?

Nếu một build “nhanh” vì dùng nhầm JAR cũ, đó không phải thành công về hiệu năng. Với cùng cấu hình và bộ dependency đã ghim, nên kiểm tra tên/phiên bản artifact được resolve và tính toàn vẹn khi có nghi vấn. Build muốn tái lập nghiêm ngặt còn phải kiểm soát nguồn artifact, metadata và toolchain.

Đặc biệt, **đóng gói một bản cache làm đầu ra cuối cùng** không thay thế cho việc xác nhận tập dependency dùng trong lần build hiện tại.

## 11. Quy ước triển khai cho dự án Ant thực tế

Một cấu trúc có thể áp dụng khi dự án bắt đầu phát triển:

```text
project/
├── build.xml               # build target và classpath
├── ivy.xml                 # dependency/version của dự án
├── ivysettings.xml         # resolver và cache policy
├── tools/                  # công cụ Ivy được ghim phiên bản, nếu chọn lưu cục bộ
├── src/
└── build/                  # output có thể xóa và tạo lại
```

Trong cấu trúc này:

- Mọi dependency trực tiếp được khai báo ở `ivy.xml` để dễ xem thay đổi.
- Một target `resolve` trung tâm cung cấp `pathid` cho compile/test/run tùy cấu hình.
- `<ivy:cachepath>` được dùng khi Ant cần JAR trên classpath; `<ivy:retrieve>` chỉ dùng khi cần bản sao vật lý để đóng gói.
- Cache Ivy sống ở vị trí có vòng đời dài hơn output build.
- CI lưu và khôi phục cache theo bộ input rõ ràng; không coi cache là nguồn chân lý về version.
- Build offline được thiết kế như một chế độ có nguồn dependency cục bộ xác định, thay vì trông chờ cache vô tình đã đủ.
- Các bản phát hành dùng repository, phiên bản, checksum và toolchain đã được kiểm soát.

Quản lý cache trong Ant vì thế là kết hợp **dependency resolution đúng**, **vị trí lưu trữ phù hợp** và **quy tắc làm mới có kiểm soát**. Khi giữ được ba nguyên tắc này, dự án giảm được việc tải lại thư viện mà vẫn duy trì đầu vào build minh bạch, an toàn và có thể tái hiện.

