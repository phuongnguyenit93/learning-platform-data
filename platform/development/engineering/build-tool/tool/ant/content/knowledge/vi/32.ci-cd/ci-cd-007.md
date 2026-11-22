# Thiết kế cache dependency và phục hồi khi cache không còn hợp lệ trong CI/CD với Apache Ant

## 1. Mục tiêu: tăng tốc build nhưng vẫn tin cậy vào dependency

Trong một pipeline **CI/CD dùng Apache Ant**, việc tải lại hàng chục hoặc hàng trăm thư viện Java mỗi lần chạy có thể tốn đáng kể thời gian và băng thông. Cache dependency giúp các lượt build kế tiếp tái sử dụng bản sao artifact đã tải. Tuy nhiên, cache có thể bị thiếu, hết hạn, sai phiên bản, hỏng nội dung hoặc chứa dependency không còn khớp với cấu hình hiện tại.

Một quy trình thiết kế tốt cần trả lời đồng thời ba câu hỏi:

1. **Cache cái gì?** Lưu đúng thư viện và metadata mà công cụ phân giải dependency dùng lại được.
2. **Khi nào được tái sử dụng?** Xác định khóa cache (cache key) và kiểm tra tính hợp lệ của dữ liệu đã restore.
3. **Nếu cache sai thì làm gì?** Xóa hoặc cách ly vùng cache có vấn đề, tải lại từ nguồn đã tin cậy, xác minh lại, rồi tiếp tục build hoặc báo lỗi rõ ràng.

Điểm quan trọng: **cache là phần tăng tốc, không phải nguồn chân lý của dependency**. Nguồn chân lý là mô tả dependency, phiên bản được khóa theo chính sách dự án, repository artifact đáng tin cậy và dữ liệu xác thực nội dung (nếu có).

Ví dụ luồng lý tưởng:

```text
Checkout đúng commit
       |
       v
Lấy cấu hình dependency + toolchain
       |
       v
Tính cache key ----> Restore nếu có snapshot phù hợp
       |                         |
       +------------+------------+
                    |
                    v
          Resolve + kiểm tra artifact
                    |
           +--------+--------+
           |                 |
        Hợp lệ           Không hợp lệ
           |                 |
           |           Dọn cache lỗi
           |                 |
           |           Resolve sạch lại
           |                 |
           |              Xác minh
           |                 |
           +--------+--------+
                    |
                    v
                 Build/test
                    |
                    v
         Lưu cache mới khi đủ điều kiện
```

Một kết quả **cache hit** chỉ cho biết hệ thống tìm được snapshot phù hợp với key. Nó không tự chứng minh file JAR trong snapshot nguyên vẹn hoặc toàn bộ dependency đúng phiên bản.

## 2. Phân biệt cache của Ant, Ivy và sản phẩm build

Apache Ant là công cụ điều phối các target và task. **Ant lõi không mặc định cung cấp kho tải dependency có cơ chế cache tập trung như các trình quản lý dependency chuyên dụng**. Tùy dự án, thư viện có thể được lấy bằng:

- **Apache Ivy:** phần mở rộng thường dùng với Ant, đọc `ivy.xml` và resolver được định nghĩa trong `ivysettings.xml`, lưu artifact/metadata đã tải tại cache (mặc định dưới `~/.ivy2/cache`, tùy cấu hình).
- **Maven Ant Tasks hoặc tập lệnh khác:** cơ chế tải và vị trí cache phụ thuộc công cụ tích hợp. Không mặc định xem cache của Maven Ant Tasks giống cache Ivy.
- **JAR đã kiểm soát trong `lib/`:** nếu các JAR được commit trực tiếp vào repository, việc checkout đã có chúng; thêm một cache CI riêng cho cùng tập JAR thường không mang lại lợi ích.
- **Lệnh tải riêng bằng `<get>` hoặc `<exec>`:** phải tự quy định nơi tải, tên file, xác thực và điều kiện dùng lại. Việc một file “đã tồn tại” chưa đủ bảo đảm nó đúng nội dung.

**Phân biệt ba loại dữ liệu:**

| Dữ liệu | Ví dụ | Có nên cache? | Lý do |
| --- | --- | --- | --- |
| **Dependency tải từ bên ngoài** | `~/.ivy2/cache`, JAR đã giải quyết từ artifact repository | Có, nếu tách biệt và kiểm tra được | Tiết kiệm download; có thể tạo lại từ nguồn gốc. |
| **Đầu ra trung gian** | `build/classes`, mã nguồn generate | Là quyết định riêng, cần phân tích đầu vào đầy đủ | Dễ mang dữ liệu cũ; không phải cache dependency. |
| **Sản phẩm phát hành** | `dist/app.jar`, ZIP triển khai | Nên dùng artifact của job/release tương ứng, không dùng như cache dependency | Cần gắn với commit và kết quả kiểm tra của lần build. |

Bài này lấy **Ant kết hợp Apache Ivy** làm ví dụ chính. Nếu dự án đang dùng công cụ khác, hãy thay đường dẫn cache và lệnh resolve theo công cụ đó, nhưng giữ các nguyên tắc về key, xác minh và khôi phục.

### Cache khác với lưu artifact

- **Cache:** có thể bị hệ thống CI loại bỏ bất kỳ lúc nào; build vẫn phải chạy được khi không có cache. Nội dung chỉ đáng dùng sau khi kiểm tra.
- **Build artifact:** đầu ra `dist/` của một job cụ thể, có thể được lưu để kiểm thử hoặc phát hành và phải liên hệ được với commit/build ID.
- **Artifact repository:** nơi xuất bản hoặc phân phối dependency/JAR có quản lý phiên bản. Nó là nguồn cấp dữ liệu cho cache, không phải bản cache của một runner.

Tránh đặt `dist/` trong khóa cache Ivy hoặc restore một JAR đầu ra từ job cũ mà không xét phiên bản mã nguồn.

## 3. Ví dụ dự án Ant sử dụng Ivy

Giả sử cấu trúc dự án:

```text
ant-cache-demo/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── tools/
│   └── ivy.jar                 # JAR Apache Ivy đã kiểm soát phiên bản
├── src/
│   └── example/
│       └── Main.java
├── ci/
│   └── dependencies.sha256    # Danh sách checksum đã duyệt
├── lib/                        # Ivy retrieve tạo khi build
├── build/                      # Output biên dịch
└── dist/                       # Artifact phát hành
```

**Giả định:** `tools/ivy.jar` đã được lấy từ bản Apache Ivy tin cậy, phiên bản được quản lý trong dự án và được xác minh checksum trước khi đưa vào repository. Đây là ví dụ kiến trúc; file Ivy JAR không xuất hiện tự động chỉ vì khai báo trong XML.

### 3.1. Khai báo dependency bằng `ivy.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info organisation="example" module="ant-cache-demo"/>

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

`rev="3.14.0"` là một phiên bản xác định. Với ứng dụng cần build tái lập, tránh khai báo phiên bản động như `latest.release` hoặc `1.+` nếu chưa có cơ chế ghi lại và cưỡng chế toàn bộ tập phiên bản đã resolve.

Khóa phiên bản trực tiếp vẫn chưa tự bảo đảm mọi dependency bắc cầu bất biến. Metadata ở repository, chính sách resolver, thay đổi artifact phía server và sự khác nhau của phiên bản Ivy vẫn cần được kiểm soát. Với yêu cầu đảm bảo mạnh, phải lưu lại **đầy đủ cây resolved dependency và checksum nội dung**.

### 3.2. Định nghĩa resolver bằng `ivysettings.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivysettings>
    <settings defaultResolver="central"/>

    <resolvers>
        <ibiblio name="central"
                 m2compatible="true"
                 root="https://repo.maven.apache.org/maven2/"/>
    </resolvers>
</ivysettings>
```

Resolver quyết định dependency được tìm ở đâu. Với hệ thống doanh nghiệp, có thể dùng repository nội bộ có quy tắc authentication/ủy quyền và artifact bất biến; không nhúng token vào `ivysettings.xml` được commit công khai.

### 3.3. Định nghĩa target resolve và build trong `build.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-cache-demo"
         default="dist"
         basedir="."
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="src.dir" location="src"/>
    <property name="build.dir" location="build"/>
    <property name="lib.dir" location="lib"/>
    <property name="dist.dir" location="dist"/>

    <taskdef uri="antlib:org.apache.ivy.ant"
             resource="org/apache/ivy/ant/antlib.xml"
             classpath="tools/ivy.jar"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
        <delete dir="${lib.dir}"/>
    </target>

    <target name="resolve">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:resolve file="ivy.xml" conf="compile"/>
        <ivy:retrieve conf="compile"
                      pattern="${lib.dir}/[organisation]/[module]/[artifact]-[revision](-[classifier]).[ext]"
                      sync="true"/>
    </target>

    <target name="compile" depends="resolve">
        <mkdir dir="${build.dir}/classes"/>
        <javac srcdir="${src.dir}"
               destdir="${build.dir}/classes"
               encoding="UTF-8"
               release="17"
               includeantruntime="false">
            <classpath>
                <fileset dir="${lib.dir}">
                    <include name="**/*.jar"/>
                </fileset>
            </classpath>
        </javac>
    </target>

    <target name="dist" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/app.jar"
             basedir="${build.dir}/classes">
            <manifest>
                <attribute name="Main-Class" value="example.Main"/>
            </manifest>
        </jar>
    </target>
</project>
```

Ví dụ dùng JDK 17 trở lên và Ant có hỗ trợ thuộc tính `release` của `javac`. Giả định `src/example/Main.java` là lớp Java hợp lệ có phương thức `main`.

Khi chạy:

```bash
ant clean resolve
ant dist
```

Ivy phân giải `ivy.xml` theo `ivysettings.xml`, sử dụng cache và tạo bản sao thư viện trong `lib/`. Sau đó Ant biên dịch và đóng gói. `<ivy:retrieve sync="true">` giúp làm sạch các tệp đã retrieve trước đây nhưng không còn thuộc tập thư viện hiện tại; chỉ dùng `sync` với **thư mục `lib/` dành riêng cho dữ liệu generate**, vì nó có thể xóa file trong vùng đích không còn khớp kết quả retrieve.

**Hai nơi lưu dữ liệu cần tách biệt:**

- **Ivy cache:** `~/.ivy2/cache` theo mặc định. Chứa artifact và metadata để tránh tải lại.
- **`lib/` của project:** tập JAR phục vụ biên dịch, được sinh từ kết quả resolve/retrieve. `clean` xóa thư mục này rồi tạo lại, còn Ivy cache vẫn có thể được tái sử dụng.

Nếu hai runner có cùng `ivy.xml` nhưng một runner dùng cache hỏng, Ivy có thể resolve không thành công hoặc retrieve ra artifact không đúng. Vì vậy cần bước kiểm tra sau khi restore, không chỉ tin vào exit code của `ant resolve`.

## 4. Thiết kế cache key: xác định đúng điều kiện tái sử dụng

Một cache key là định danh dùng để tìm snapshot tương ứng. Key cần phản ánh các yếu tố **có thể làm dữ liệu cache không còn tương thích hoặc không còn đúng**.

Ví dụ cấu trúc:

```text
ivy-v3-linux-jdk17-ant1.10-<hash-cua-mo-ta-dependency-va-cau-hinh>
 |    |     |       |       |
 |    |     |       |       +-- dấu vân tay của input liên quan
 |    |     |       +---------- họ phiên bản Ant
 |    |     +------------------ JDK/toolchain
 |    +------------------------ nền tảng
 +----------------------------- namespace/schema cache
```

Các thành phần đáng cân nhắc:

| Thành phần | Đưa vào key khi nào | Vì sao |
| --- | --- | --- |
| Namespace `ivy-v3` | Luôn nên có | Có cách vô hiệu hóa toàn bộ cache cũ khi thay chính sách hoặc phát hiện dữ liệu không tin cậy. |
| Hệ điều hành/kiến trúc | Khi có artifact native, metadata/tool khác nhau hoặc chính sách CI yêu cầu | Tránh dùng chung cache không tương thích; Java thuần không phải lúc nào cần tách theo OS. |
| JDK và phiên bản Ant/Ivy | Khi ảnh hưởng cách phân giải hoặc cấu trúc cache | Giảm rủi ro dùng metadata/cache được sinh bằng tool khác. |
| `ivy.xml` | Gần như luôn có | Thay tên, version, configuration hoặc quan hệ dependency phải sinh key mới. |
| `ivysettings.xml` | Khi chứa resolver, cache configuration và policy | Thay kho artifact/chính sách phân giải làm thay đổi kết quả. |
| Lock/resolution/checksum manifest | Nếu dự án dùng | Thay nội dung đã pin phải làm cache cũ hết hiệu lực. |
| Ivy JAR hoặc tệp khai báo toolchain | Nếu được quản lý trong repo | Đảm bảo phiên bản công cụ đúng với key. |

**Không đưa mặc định mọi file nguồn Java vào key của cache dependency.** Khi thay `Main.java` nhưng tập dependency và resolver giữ nguyên, cache vẫn có thể dùng; cache không phải bản sao đầu ra biên dịch.

Tuy vậy, nếu cấu hình Ant quyết định dependency dựa trên mã nguồn, thuộc tính môi trường hoặc file khác ngoài `ivy.xml`, những input đó cũng phải tham gia key hoặc được xác thực độc lập.

### Thế nào là key quá rộng hoặc quá hẹp?

- **Quá hẹp về thông tin:** dùng key cố định `ivy-cache` dù đổi `ivy.xml` hoặc resolver; snapshot cũ có thể được lấy lại trong tình huống không tương thích.
- **Quá rộng về input:** dùng hash của toàn bộ repository cho mỗi cache dependency; thay một dòng comment Java cũng khiến cache miss, giảm lợi ích.
- **Restore fallback quá thoáng:** lấy “cache gần giống” qua tiền tố `ivy-` dù toolchain/resolver khác nhau. Nếu có fallback, phải cho resolve và xác minh lại toàn bộ; không coi cache fallback là đã hợp lệ.

Key là **bộ lọc ứng viên**, không phải cơ chế chứng minh nội dung file trong cache chính xác.

## 5. Chính sách tính hợp lệ: khi nào cache được dùng?

Nên xem cache là một trạng thái có thể chuyển đổi:

| Trạng thái | Dấu hiệu | Hành động |
| --- | --- | --- |
| **MISS** | Không tìm thấy snapshot theo key | Resolve từ repository chuẩn; sau khi thành công mới lưu cache. |
| **HIT_UNVERIFIED** | Restore snapshot thành công | Chạy resolve/retrieve và kiểm tra dependency. |
| **VALID** | Tập artifact và checksum được yêu cầu đều khớp | Dùng cho compile/test/package. |
| **STALE** | Descriptor, settings hoặc phiên bản thay đổi | Tạo key mới và resolve lại. |
| **CORRUPT** | JAR không mở được, digest sai, metadata bất thường hoặc tệp thiếu | Dọn cache chuyên dụng, tải lại sạch, xác minh lại. |
| **UNAVAILABLE** | Repository bên ngoài không truy cập được khi cần tải lại | Fail hoặc tuân theo quy trình offline có kiểm soát; không tự coi cache nghi vấn là đáng tin. |

Một số nguyên nhân làm cache không còn hợp lệ:

1. **Dependency được nâng phiên bản:** key phải thay đổi cùng descriptor.
2. **Đổi repository/mirror:** cache chứa artifact từ nguồn cũ; cần refresh theo policy và kiểm tra nội dung.
3. **Cache upload/download bị lỗi:** file JAR/trang metadata bị cắt hoặc không đọc được.
4. **Nội dung artifact bị thay thế phía server:** cùng tọa độ artifact nhưng digest khác; đây là sự cố nguồn cung cấp, không chỉ là vấn đề tốc độ cache.
5. **Metadata đã cũ:** đặc biệt với phiên bản `SNAPSHOT` hoặc version động; resolver có thể dùng kết quả cũ trong thời gian nhất định.
6. **Hai job cùng thao tác trên thư mục chung:** dữ liệu bị ghi chồng, xóa giữa chừng hoặc race condition.
7. **Thay đổi công cụ:** bản Ivy khác có cấu trúc metadata hoặc cách resolve khác.
8. **Cache không an toàn:** dữ liệu đến từ nguồn/job không tin cậy hoặc chứa artifact không qua kiểm tra.

### Cache hit không đồng nghĩa cache hợp lệ

Đây là khác biệt thiết kế cốt lõi:

```text
RESTORE HIT
  |
  v
Có file trong cache? -- không --> resolve lại
  |
 có
  v
Đúng tập dependency? -- không --> xử lý miss/stale
  |
 đúng
  v
Checksum/artifact hợp lệ? -- không --> xóa cache + tải lại
  |
 đúng
  v
Cho phép build
```

Có thể cần chạy resolve để biết chính xác tập dependency và phát hiện version bắc cầu. Nếu làm CI cần bảo đảm mạnh, quá trình resolve phải dựa trên dependency đã pin, repository tin cậy và không lấy phiên bản mới ngoài dự kiến.

## 6. Xác thực artifact: checksum, số lượng và nguồn gốc

Chỉ kiểm tra tệp tồn tại hoặc dung lượng lớn hơn 0 là chưa đủ. Tốt hơn là kiểm tra digest SHA-256 đã được chấp thuận.

Ví dụ `ci/dependencies.sha256`:

```text
<64-ky-tu-SHA256-da-xac-minh>  lib/org.apache.commons/commons-lang3/commons-lang3-3.14.0.jar
```

Dòng trên là **mẫu định dạng**, chưa thể chạy trực tiếp cho đến khi thay placeholder bằng checksum SHA-256 thật của artifact đã được duyệt. Không tự tính digest từ chính cache nghi vấn rồi ghi đè manifest và gọi đó là “xác minh”, vì như vậy sẽ mặc nhiên tin dữ liệu đang cần kiểm chứng.

Với Linux runner có `sha256sum`:

```bash
sha256sum -c ci/dependencies.sha256
```

Công cụ trả mã thoát khác 0 nếu file đã liệt kê bị thiếu hoặc checksum không khớp. Nếu có nhiều dependency, manifest phải mô tả **tất cả artifact cần thiết**, bao gồm cả dependency bắc cầu hoặc classifier mà build thực sự sử dụng.

**Lưu ý:** `sha256sum -c` xác minh những file **có liệt kê**, chứ không tự phát hiện một file JAR phát sinh thêm ngoài manifest. Với quy trình nghiêm ngặt, hãy so sánh thêm **tập đường dẫn artifact sau retrieve** với danh mục được phê duyệt, và từ chối file lạ. Bản ghi resolution của Ivy hoặc manifest do dự án quản lý có thể dùng để xác định danh mục này.

Bảng lựa chọn kiểm tra:

| Phương pháp | Phát hiện | Chưa đủ để bảo đảm |
| --- | --- | --- |
| `-f`/`available` | File có tồn tại | Nội dung đúng hoặc tin cậy |
| Kích thước file | File rỗng/cắt ngắn ở một số trường hợp | Nội dung không bị thay đổi |
| `jar tf ...` | Archive có thể đọc cấu trúc ở mức cơ bản | Archive được cấp bởi đúng nhà phát hành, digest khớp |
| SHA-256 so với manifest độc lập | Byte khác với bản đã duyệt | Manifest có đáng tin hay không; có file thừa hay không |
| Danh mục artifact + SHA-256 + thông tin nguồn | Đúng tập artifact và đúng nội dung đã kiểm soát | Toàn bộ hành vi của ứng dụng khi chạy |

Khi có chữ ký của artifact hoặc kho lưu trữ hỗ trợ xác thực nguồn gốc, nên bổ sung bước kiểm tra phù hợp với chính sách dự án. SHA-256 chứng minh **nội dung so với giá trị kỳ vọng**, không tự chứng minh ai đã xuất bản artifact.

## 7. Quy trình phục hồi cache khi không còn hợp lệ

Đặt quy tắc khôi phục rõ ràng để pipeline không bị mắc kẹt vào một snapshot hỏng:

1. **Restore:** hệ thống CI khôi phục cache theo key hiện tại nếu có.
2. **Resolve và retrieve:** chạy target Ivy với cấu hình đã quản lý; không tin rằng file cache nào cũng đủ dùng.
3. **Verify:** đối chiếu artifact đã tải/trích xuất với manifest checksum và danh mục cần có.
4. **Phát hiện lỗi:** nếu resolve hoặc verify thất bại, ghi log tệp/lý do cụ thể và coi cache là nghi vấn.
5. **Loại bỏ cache của dependency:** xóa riêng thư mục cache Ivy đã xác định, cùng đầu ra `lib/` sinh lại nếu cần; tránh xóa workspace hoặc directory chứa dữ liệu người dùng.
6. **Tải lại sạch:** thực hiện resolve/retrieve từ repository được duyệt, rồi kiểm tra lại đúng cùng tiêu chí.
7. **Tiếp tục hoặc fail:** nếu pass, compile/test/package; nếu vẫn lỗi, **dừng pipeline** với nguyên nhân thay vì dùng JAR chưa được xác thực.
8. **Quản lý snapshot remote bị hỏng:** nếu cache đã được lưu bằng key bất biến trên CI, thay namespace/key hoặc xóa cache qua cơ chế quản trị được phép để job sau không restore mãi bản cũ.

Giới hạn khôi phục tự động **một lượt tải lại sạch** là hợp lý cho lỗi cache. Nếu repository đang mất mạng, credential hết hạn hoặc descriptor sai, xóa cache lặp vô hạn sẽ không giải quyết được và có thể làm sự cố tệ hơn.

### Sơ đồ chuyển trạng thái

```text
            +------------------+
            |   Bắt đầu job    |
            +---------+--------+
                      |
                      v
              Restore cache key
                      |
                      v
              Resolve + Verify
                  /         \
               PASS         FAIL
                |             |
                |     Xóa cache Ivy cục bộ
                |             |
                |      Resolve lại 1 lần
                |             |
                |       Verify lại
                |         /    \
                |      PASS    FAIL
                |        |       |
                +--------+       v
                     |        Stop CI
                     v
               Compile + Test
                     |
                     v
             Lưu cache nếu được phép
```

**Phạm vi xóa:** chỉ xóa thư mục cache có thể tái tạo và đã được dự án/runner dành riêng. Với runner dùng chung, cần bảo vệ cache của job khác bằng cấu hình riêng cho từng pipeline hoặc namespace; không chạy lệnh xóa tràn toàn bộ `~/.m2`, `~/.ivy2` hay `$HOME`.

## 8. Ví dụ pipeline GitHub Actions: restore → verify → recovery → save

Ví dụ sau dành cho **runner Ubuntu tạm thời** có truy cập Internet, repository chứa bộ file Ant/Ivy ở phần 3 và một file `ci/dependencies.sha256` đã có các checksum thật. Đây là bản mẫu để điều chỉnh cho dự án; số phiên bản công cụ phải được cập nhật theo runtime được quản lý.

Tạo `.github/workflows/ant-build.yml`:

```yaml
name: Ant CI with verified Ivy cache

on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Install Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant
          ant -version
          java -version

      - name: Restore Ivy dependency cache
        id: ivy-cache
        uses: actions/cache/restore@v4
        with:
          path: ~/.ivy2/cache
          key: ivy-v1-${{ runner.os }}-jdk17-ant1.10-${{ hashFiles('tools/ivy.jar', 'ivy.xml', 'ivysettings.xml', 'ci/dependencies.sha256') }}

      - name: Resolve, verify and recover if needed
        shell: bash
        run: |
          set -euo pipefail

          resolve_and_verify() {
            ant -noinput clean resolve || return 1
            sha256sum -c ci/dependencies.sha256 || return 1
          }

          if resolve_and_verify; then
            echo "Dependency verified on first attempt."
          else
            echo "Dependency cache/resolve failed; retrying once with clean Ivy cache."
            rm -rf -- "$HOME/.ivy2/cache"
            resolve_and_verify
            echo "Dependency verified after clean resolve."
          fi

      - name: Build artifact
        run: ant -noinput dist

      - name: Save valid Ivy cache
        if: ${{ success() && steps.ivy-cache.outputs.cache-hit != 'true' }}
        uses: actions/cache/save@v4
        with:
          path: ~/.ivy2/cache
          key: ${{ steps.ivy-cache.outputs.cache-primary-key }}
```

### Giải thích thiết kế của pipeline

**1. Khóa cache gồm descriptor, settings và checksum manifest.** Nếu các file này thay đổi, hash thay đổi. Tiền tố `ivy-v1` là phiên bản chính sách cache. Ví dụ `ant1.10` mang tính minh họa; với pipeline production, hãy cố định phiên bản Ant/Ivy thực tế hoặc thay token này bằng thông tin toolchain được quản lý chính xác.

**2. Không dùng `restore-keys` quá rộng.** Trong bài này cache chỉ được restore khi có key khớp. Nếu muốn dùng cache fallback, phải coi nó là cache chưa xác thực và resolve + kiểm tra toàn bộ.

**3. `clean` và Ivy cache là hai phạm vi khác nhau.** `ant clean resolve` xóa `build/`, `dist/` và `lib/` theo target ví dụ, nhưng không xóa `~/.ivy2/cache`. Nhờ đó có thể thử dùng lại cache, rồi tạo một lượt resolve sạch khi thất bại.

**4. Hàm kiểm tra có mã thoát tin cậy.** Mỗi lệnh trong `resolve_and_verify` đều có `|| return 1`. Nhờ vậy, nếu Ant thất bại, script không vô tình chạy tiếp và trả PASS chỉ vì một lệnh kiểm tra cũ thành công.

**5. Retry chỉ chạy một lần.** Sau khi xóa thư mục Ivy cache, nếu tải lại hoặc đối chiếu checksum vẫn lỗi, bước CI dừng. Không gọi lỗi compile/test là “hỏng cache”, vì khôi phục chỉ bao quanh giai đoạn resolve và verify.

**6. Chỉ lưu sau khi build thành công.** Bước `actions/cache/save` chạy nếu job thành công và chưa có exact hit. Nếu build fail, cache chưa được ghi. Tùy dự án, có thể quyết định lưu cache đã được xác minh trước test; nhưng quyết định đó phải tách rõ trạng thái dependency valid khỏi trạng thái phần mềm pass test.

**7. Không ghi đè remote cache trùng key.** Nhiều hệ thống cache CI, trong đó có GitHub Actions cache, xem một entry theo key đã tạo là bất biến. Nếu key có snapshot hỏng, lượt hiện tại có thể tự phục hồi cục bộ nhưng **không thay thế được snapshot đã tồn tại dưới cùng key**. Phải đổi `ivy-v1` thành `ivy-v2` hoặc quản trị/xóa cache lỗi theo quyền được cấp để lần sau không lại restore nó.

**8. Cache dữ liệu có nguồn gốc không đáng tin vẫn cần xác thực.** Không đưa token, secret, cấu hình xác thực hoặc file nhạy cảm vào cache. Job từ pull request bên ngoài có thể chịu các quy tắc quyền truy cập khác nhau; không dùng cache làm kênh truyền dữ liệu bí mật hay artifact chưa được duyệt giữa các nhánh.

**9. Công cụ phải thực sự có sẵn.** Ví dụ dùng `apt-get` để cài Ant trên Ubuntu; phiên bản có thể thay đổi theo package repository. Với yêu cầu tái lập chặt, hãy dùng image hoặc công cụ được pin chính xác và kiểm tra checksum gói cài. `tools/ivy.jar` cũng cần tồn tại như phần giả định của dự án.

### Vì sao không tự động cập nhật checksum khi lỗi?

Nếu bước kiểm tra sai digest rồi chạy:

```bash
# KHÔNG được tự động làm thế này sau khi cache thất bại:
sha256sum lib/**/*.jar > ci/dependencies.sha256
```

thì pipeline sẽ biến các byte **chưa được tin cậy** thành “đầu vào chuẩn” mới. Cách đúng là giữ manifest đã duyệt, tải lại từ nguồn chính thức và **fail** nếu nội dung vẫn khác. Việc thay manifest checksum thuộc quy trình nâng dependency có review, không phải thao tác tự chữa cache.

## 9. Khi cache remote đã hỏng: thay key và kiểm soát vòng đời

Giả sử bản `ivy-v1-linux-...` bị hỏng. Pipeline chạy như sau:

```text
Job N:
  RESTORE ivy-v1-... -> HIT nhưng JAR lỗi
  Xóa local ~/.ivy2/cache
  Resolve lại -> PASS
  Build -> PASS
  Cache save cùng key -> không thể ghi đè entry cũ

Job N+1:
  RESTORE ivy-v1-... -> lại HIT cache lỗi
  Lại phải phục hồi cục bộ
```

Cách sửa bền vững:

- **Bump namespace:** đổi `ivy-v1` thành `ivy-v2` trong workflow; job mới có key mới nên tự tải lại và lưu snapshot lành.
- **Xóa cache hỏng bằng quyền quản trị được phép:** dùng UI/API của nhà cung cấp CI khi có chủ đích, nếu cần thu hồi ngay.
- **Rà nguyên nhân:** xác định JAR bị cắt trong lần save, resolver trả nội dung sai, key thiếu input hay cache bị nhiễm từ job khác.
- **Ngăn lặp lại:** bổ sung checksum, khóa phiên bản, phân vùng cache, hoặc thay policy lưu.

Nên ghi nhận **cache key, cache hit/miss, thời điểm resolve, checksum kết quả và có retry hay không** trong log build. Không đưa credential, URL chứa secret hay dữ liệu riêng tư vào log.

### TTL và cơ chế dọn của nhà cung cấp CI

Cache có thể bị xóa do giới hạn dung lượng hoặc chính sách lưu giữ. Pipeline phải xem đây là **MISS bình thường**, tải lại dependency và tiếp tục. Không xây logic “job bắt buộc phải có cache”.

Nếu dependency dùng `SNAPSHOT` hoặc version thay đổi theo thời gian, key chỉ dựa trên `ivy.xml` có thể không đổi trong khi artifact thực tế thay đổi. Các lựa chọn là: chuyển sang bản release bất biến, ghi đầy đủ resolved version/digest, hoặc dùng chính sách refresh/invalidation có thời hạn được thiết kế riêng. Không nên coi cache của snapshot động là cơ sở tái lập build.

## 10. Tách cache theo phạm vi tin cậy và tính tương thích

Cache lưu file được đưa vào classpath biên dịch và có thể bị công cụ build đọc/giải nén. Vì vậy thiết kế cache còn liên quan tới tính toàn vẹn và kiểm soát truy cập.

### Phạm vi nên phân tách

- **Hệ điều hành và kiến trúc** khi có dependency native hoặc khác cấu trúc file.
- **Phiên bản Ivy/toolchain** khi metadata hoặc resolver có thay đổi đáng kể.
- **Project/module hoặc tập dependency** nếu nhiều dự án dùng chung runner nhưng không được phép đọc dữ liệu của nhau.
- **Môi trường tin cậy** (nhánh chính, fork pull request, release job) theo chính sách của CI. Không nâng quyền tin cậy chỉ vì key giống nhau.

Với cache lưu ở runner tự quản lý, tránh nhiều job cùng ghi vào đúng một thư mục `~/.ivy2/cache` trong lúc resolve. Có thể cấp **thư mục cache riêng cho job**, hoặc thiết lập cơ chế đồng bộ khi thực sự cần chia sẻ; không dựa vào may mắn về thứ tự chạy.

### Secret và cache

Không cache các tệp chứa token repository, credential XML, `settings.xml` có mật khẩu dạng rõ hay biến môi trường đã được ghi ra file. Chỉ cache artifact và metadata cần thiết. Chứng thực truy cập repository nên được cấp qua secret của CI ở bước chạy và được loại khỏi đầu ra lưu cache.

Nếu nhóm cần tốc độ tốt ở nhiều runner, cân nhắc **artifact proxy/repository manager** nội bộ có chính sách lưu trữ và kiểm tra nguồn gốc. Đây là lớp dùng chung khác với cache cục bộ của một job.

## 11. Quan sát hiệu quả cache mà không che giấu lỗi

Cache tốt cần có **số liệu**. Ngoài trạng thái PASS/FAIL, ghi nhận:

| Chỉ số | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| Cache hit rate | Tỷ lệ job restore được snapshot | Hit nhiều chưa chắc valid nhiều. |
| Cache validation pass rate | Tỷ lệ cache restore vượt qua kiểm tra | Phản ánh chất lượng cache thực tế. |
| Resolve/download duration | Thời gian resolve dependency | Cache hợp lệ thường giúp giảm thời gian tải. |
| Retry/recovery count | Số job phải xóa cache và tải lại | Tăng đột biến cho thấy lỗi cache, key hoặc repository. |
| Cache size | Dung lượng snapshot | Quá lớn gây restore chậm hơn tải mới. |
| Dependency checksum mismatch | Số artifact khác digest mong đợi | Cần điều tra ngay, có thể là thay đổi nguồn cung cấp. |
| Offline/repository failure | Số job không thể lấy dependency mới | Phân biệt sự cố mạng với hỏng nội dung cache. |

Ví dụ log đủ hữu ích:

```text
CACHE_KEY=ivy-v2-linux-jdk17-...
CACHE_RESTORE=HIT
DEPENDENCY_RESOLVE=SUCCESS
DEPENDENCY_VERIFY=FAIL (commons-lang3-3.14.0.jar)
RECOVERY_ATTEMPT=1
LOCAL_CACHE_PURGE=SUCCESS
DEPENDENCY_RESOLVE_AFTER_PURGE=SUCCESS
DEPENDENCY_VERIFY_AFTER_PURGE=SUCCESS
BUILD_RESULT=SUCCESS
REMOTE_CACHE_ACTION=INVALIDATE_KEY_REQUIRED
```

Đây là **ví dụ log minh họa**, không phải dòng log Ivy tự in nguyên văn. Khi triển khai thực, có thể dùng output của script để chuẩn hóa các trường này.

Với job thất bại sau retry, nên lưu phần log và report resolution **không chứa secret**. Chỉ lưu JAR hỏng làm bằng chứng khi chính sách bảo mật cho phép; trong nhiều trường hợp, tên artifact, expected/actual hash và log tải đã đủ để chẩn đoán.

## 12. Tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Cache MISS ở mọi job dù dependency không đổi | Key có hash nguồn Java/commit liên tục, sai đường dẫn cache, không có bước save | Chỉ đưa input dependency liên quan vào key; kiểm tra vị trí `~/.ivy2/cache` và điều kiện save. |
| Cache HIT nhưng `ivy:resolve` tải lại nhiều file | Cache metadata chưa đủ, cấu hình resolver thay đổi, TTL refresh, Ivy cache path không trùng | Kiểm tra setting, log resolver và đường dẫn cache thật. |
| Cache HIT, `jar tf` lỗi | JAR hỏng/truncated | Xóa cache Ivy chuyên dụng, resolve sạch, xác minh digest. |
| Checksum sai sau khi đã xóa cache | Artifact nguồn đã đổi, manifest không còn khớp, proxy trả dữ liệu sai | Fail; kiểm tra nguồn artifact và manifest độc lập, không tự cập nhật checksum. |
| `ivy:retrieve` còn JAR của version cũ trong `lib/` | Vùng retrieve chưa làm sạch hoặc nhiều target cùng ghi | Dùng `clean` đúng vùng và `sync="true"` cho thư mục generate chuyên dụng. |
| Compile chỉ fail khi build trên runner khác | Cache/toolchain/OS không tương thích, dependency native hoặc input không được pin | Tách key theo môi trường và xác minh dependency/toolchain. |
| Cache hỏng lặp lại mỗi job mặc dù recovery pass | Remote snapshot cùng key là bất biến và vẫn được restore | Đổi namespace cache hoặc xóa entry lỗi qua quyền quản trị. |
| Pipeline fail khi kho dependency mất mạng và cache miss | Cache không đảm bảo có sẵn; không thể tải file thiếu | Retry mạng giới hạn, theo dõi kho; không bỏ qua kiểm tra tính đúng. |
| Build lâu hơn sau khi bật cache | Dung lượng cache quá lớn, restore/upload đắt | Giảm scope, tránh cache `build/` và đầu ra không cần thiết. |
| Dữ liệu bí mật xuất hiện trong cache | Cache sai phạm vi thư mục | Di chuyển credential ra secret, xóa snapshot đã lộ theo quy trình quản lý. |
| Hai job ghi cache local cùng lúc và file hỏng | Tranh chấp thư mục dùng chung | Tách cache theo job hoặc đồng bộ truy cập có kiểm soát. |

## 13. Bài thực hành: chủ động gây cache miss và phục hồi

### Bài A — Đo lợi ích của cache hợp lệ

1. Chuẩn bị `ivy.xml` với phiên bản dependency cố định và `ci/dependencies.sha256` đã xác minh.
2. Chạy `ant clean resolve` với cache trống, ghi lại thời gian.
3. Chạy lại với cache đang có và cùng đầu vào, ghi thời gian resolve.
4. Đối chiếu checksum artifact cả hai lần và ghi nhận có file nào được tải lại không.

**Kỳ vọng:** kết quả dependency phải giống nhau; thời gian có thể cải thiện tùy network, metadata policy và tốc độ đĩa. Không coi tốc độ tăng là bằng chứng bảo toàn nội dung.

### Bài B — Thay version, kiểm tra key

1. Đổi dependency version trong `ivy.xml` theo một bản có thật.
2. Cập nhật manifest checksum sau khi đã review artifact mới.
3. Quan sát key thay đổi, cache cũ không được restore theo exact key.
4. Chạy resolve và compile; xác nhận `lib/` chứa đúng version được yêu cầu.

**Kỳ vọng:** thay đổi dependency làm vô hiệu hóa snapshot cũ ngay từ key.

### Bài C — Làm hỏng cache trong môi trường thử nghiệm

Trên runner/sandbox **dành riêng cho bài thực hành**, sau một lần tải dependency thành công, sao lưu và cố tình làm hỏng một JAR trong thư mục cache chỉ để kiểm thử. Không sửa trực tiếp cache dùng chung của nhóm hoặc snapshot từ môi trường production.

1. Chạy workflow restore/resolve/verify.
2. Quan sát lỗi checksum, lỗi đọc JAR hoặc lỗi retrieve.
3. Kiểm tra bước cleanup chỉ xóa vùng Ivy cache chuyên dụng.
4. Quan sát lần resolve sạch được gọi **một lần**.
5. Xác nhận artifact sau tải lại khớp manifest; nếu không, pipeline dừng.

**Kỳ vọng:** cache hỏng không bao giờ được xem là dependency hợp lệ chỉ vì bước restore đã báo HIT.

### Bài D — Mô phỏng source repository không khả dụng

Cấu hình resolver của một dự án thử nghiệm trỏ tới kho mô phỏng tạm thời không thể truy cập. Dùng cache trống để quan sát build fail, rồi khôi phục kết nối. Không dùng bản JAR không có checksum thay thế chỉ nhằm làm job xanh.

**Kỳ vọng:** phân biệt **thiếu cache**, **hỏng cache** và **source không khả dụng** trong log.

### Bài E — Cache key bất biến

Trong một pipeline thử nghiệm, tạo một snapshot cache lỗi rồi cho job retry sạch thành công. Quan sát rằng save không ghi đè được key cũ. Sau đó tăng namespace từ `ivy-v1` sang `ivy-v2` và xác nhận job lưu được snapshot mới.

**Kỳ vọng:** hiểu vì sao phục hồi cục bộ và vô hiệu hóa cache remote là hai thao tác khác nhau.

## 14. Các quyết định cần chốt khi đưa vào CI/CD thực tế

Trước khi đưa thiết kế vào môi trường nhóm, cần xác định cụ thể:

1. **Cơ chế dependency:** dự án dùng Ivy hay công cụ khác? File nào là nguồn chân lý của dependency?
2. **Phạm vi cache:** thư mục cache nào được phép xóa và upload? Có tách khỏi source, secret và output build không?
3. **Thành phần key:** phiên bản công cụ, OS, descriptor, resolver, checksum manifest và số phiên bản chính sách cache.
4. **Nguyên tắc bất biến:** dependency có pin đầy đủ hay dùng `SNAPSHOT`/version động? Artifact repository có cho phép thay file cùng tọa độ không?
5. **Chính sách xác minh:** kiểm tra SHA-256, danh mục artifact và nguồn cung cấp bằng dữ liệu đã được phê duyệt.
6. **Cơ chế recovery:** tối đa một lần xóa cache cục bộ và resolve lại; lỗi lặp dừng CI.
7. **Chính sách sửa cache remote:** key bất biến được bump namespace hoặc xóa entry lỗi theo quyền được cấp.
8. **Phạm vi tin cậy:** runner, branch, fork PR, artifact native, credential và cache có thể bị thao túng.
9. **Giám sát:** log key, hit/miss, checksum mismatch, số lần recovery và thời gian resolve.

### Câu hỏi tự kiểm tra

- Vì sao `actions/cache` báo HIT vẫn chưa đủ để sử dụng dependency cho compile?
- `~/.ivy2/cache` khác thư mục `lib/` mà `ivy:retrieve` tạo ra ở chỗ nào?
- Khi thay `ivysettings.xml` hoặc phiên bản Ivy, cache key có cần thay đổi không?
- Vì sao việc tự ghi lại checksum từ chính file vừa restore có thể làm mất ý nghĩa xác minh?
- Nếu lần tải lại sạch vẫn sai checksum, nên dừng hay tiếp tục build?
- Vì sao xóa cache cục bộ chưa chắc loại bỏ được snapshot hỏng đã lưu trên dịch vụ CI?
- Khi nào dùng cache offline là chấp nhận được, và phải có bằng chứng nào về nội dung dependency?

## 15. Kết luận

Thiết kế cache dependency cho Apache Ant trong CI/CD cần lấy **đúng dependency và khả năng phục hồi** làm tiêu chuẩn trước tiên. Cache Ivy giúp tăng tốc resolve nhưng không tự bảo đảm nội dung hoặc phiên bản. Một luồng đáng tin cậy sẽ khóa đầu vào, tính key đủ thông tin, restore có điều kiện, resolve và kiểm tra checksum, chỉ build từ artifact hợp lệ, rồi có đường **xóa cache lỗi và tải lại một lần** trước khi fail rõ ràng. Khi cache remote đã hỏng và key bất biến, cần vô hiệu hóa key cũ để lỗi không lặp qua các job tiếp theo.
