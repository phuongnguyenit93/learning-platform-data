# Tách cấu hình công cụ, tệp loại trừ và báo cáo khỏi mã nguồn

Trong một dự án Java, các công cụ kiểm tra chất lượng mã thường cần nhiều loại file đi kèm: file cấu hình quy tắc, danh sách file hoặc dòng được miễn kiểm tra, cấu hình dependency của công cụ và báo cáo kết quả. Nếu đặt tất cả những file này lẫn trong thư mục mã nguồn, dự án sẽ khó phân biệt đâu là sản phẩm của ứng dụng, đâu là cấu hình phục vụ build và đâu là kết quả sinh ra sau mỗi lần chạy.

Với Apache Ant, có thể tổ chức riêng ba nhóm: **cấu hình công cụ**, **tệp loại trừ/miễn trừ**, và **báo cáo được sinh ra**. Các file cấu hình được quản lý cùng repository để cả nhóm dùng chung quy tắc; các tệp loại trừ ghi lại ngoại lệ có chủ đích; báo cáo được tạo vào thư mục build để dễ thu thập trong CI và có thể xóa, tạo lại mà không ảnh hưởng mã nguồn.

## 1. Vì sao cần tách các file chất lượng mã khỏi source?

Giả sử dự án dùng Checkstyle để kiểm tra quy ước viết Java, PMD để tìm một số dạng code smell và SpotBugs để phân tích bytecode. Mỗi công cụ có thể cần:

- Một file quy định rule nào được bật, mức độ nghiêm ngặt và tham số của rule.
- Một file loại trừ những file hoặc cảnh báo cụ thể có lý do được chấp nhận.
- Một thư mục đầu ra để lưu kết quả XML, HTML hoặc định dạng mà CI đọc được.
- Một số JAR hoặc task adapter để Ant gọi công cụ.

Nếu để cấu hình trong `src/main/java`, file XML cấu hình có thể bị coi như tài nguyên ứng dụng hoặc bị đưa nhầm vào JAR. Nếu lưu báo cáo ngay cạnh source, mỗi lần chạy sẽ làm working tree xuất hiện nhiều file sinh tự động. Nếu bỏ tệp loại trừ rải rác trong buildfile, rất khó biết một ngoại lệ tồn tại vì lý do gì và ai đã phê duyệt.

Tách riêng giúp:

1. **Giữ source tree tập trung vào mã ứng dụng và test.** Công cụ phân tích đọc source, nhưng file cấu hình của nó không trở thành source của ứng dụng.
2. **Quản lý quy tắc tập trung.** Nhóm có thể xem và review thay đổi rule qua Git.
3. **Ghi lại ngoại lệ có chủ đích.** Tệp suppression/exclusion cho biết phạm vi nào được miễn kiểm tra và lý do.
4. **Tạo báo cáo ở vị trí ổn định.** CI biết nơi lấy kết quả mà không phải tìm trong thư mục source.
5. **Dễ làm sạch và tái tạo.** Có thể xóa thư mục `build` rồi chạy lại mà không mất cấu hình chất lượng mã.

## 2. Cấu trúc thư mục đề xuất

Một cấu trúc đơn giản có thể tổ chức như sau:

```text
hello-ant/
├── build.xml
├── config/
│   └── quality/
│       ├── checkstyle/
│       │   ├── checkstyle.xml
│       │   ├── checkstyle.properties
│       │   └── suppressions.xml
│       ├── pmd/
│       │   └── ruleset.xml
│       └── spotbugs/
│           └── exclude-filter.xml
├── src/
│   ├── main/java/
│   └── test/java/
├── lib/
│   └── quality-tools/
│       └── (các JAR cần thiết cho công cụ nếu dự án quản lý local)
└── build/
    └── reports/
        └── quality/
            ├── checkstyle/
            ├── pmd/
            └── spotbugs/
```

Ý nghĩa của từng khu vực:

| Đường dẫn | Nội dung | Có nên quản lý trong Git? |
|---|---|---|
| `src/main/java` | Mã ứng dụng | Có |
| `src/test/java` | Mã kiểm thử | Có |
| `config/quality/checkstyle` | Rule, property và suppression của Checkstyle | Có |
| `config/quality/pmd` | Rule set của PMD | Có |
| `config/quality/spotbugs` | Bộ lọc cảnh báo SpotBugs | Có |
| `lib/quality-tools` | JAR công cụ nếu dự án chọn lưu dependency tại chỗ | Tùy cách quản lý dependency; không commit JAR tải tự động nếu chính sách dự án không yêu cầu |
| `build/reports/quality` | Báo cáo sinh ra từ mỗi lần chạy | Thường không; đưa vào `.gitignore` và lưu dưới dạng CI artifact khi cần |

Không bắt buộc phải dùng đúng tên thư mục trên. Điều quan trọng là cấu hình được lưu ở một vị trí ổn định, tách khỏi source; báo cáo nằm trong vùng output có thể tái tạo; và buildfile tham chiếu các vị trí đó bằng property thay vì ghi đường dẫn tuyệt đối trên máy cá nhân.

## 3. Phân biệt cấu hình, loại trừ và báo cáo

Ba nhóm file thường bị nhầm lẫn vì đều liên quan đến công cụ chất lượng mã, nhưng vai trò khác nhau:

| Nhóm | Câu hỏi mà file trả lời | Ví dụ |
|---|---|---|
| Tool configuration | Công cụ phải kiểm tra theo những quy tắc nào? | `checkstyle.xml`, `ruleset.xml` |
| Exclusion/suppression | File hoặc cảnh báo cụ thể nào được bỏ qua, trong phạm vi nào? | `suppressions.xml`, `exclude-filter.xml`, exclude pattern của FileSet |
| Report | Lần chạy vừa rồi phát hiện điều gì? | `checkstyle-result.xml`, `pmd-report.html`, báo cáo SpotBugs |

File cấu hình và file suppression thường là đầu vào được review và lưu cùng source control. Report là đầu ra được tạo theo từng lượt chạy; nó thường không cần nằm trong source tree hoặc được commit như cấu hình.

Một cách ghi nhớ:

```text
Mã nguồn + cấu hình + phạm vi loại trừ
                 |
                 v
        Công cụ chất lượng mã
                 |
                 v
          Báo cáo trong build/
```

Buildfile chỉ điều phối vị trí và thứ tự chạy. Nội dung rule chi tiết nên nằm trong file cấu hình riêng của từng công cụ.

## 4. Hai loại loại trừ cần phân biệt

Khi nói “loại trừ file”, có ít nhất hai nhu cầu khác nhau.

### 4.1. Loại cả file khỏi phạm vi phân tích

Ví dụ, không muốn phân tích mã được sinh tự động, thư viện vendor được copy vào repository hoặc mã trong thư mục build:

```xml
<fileset dir="${src.main.dir}">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/vendor/**"/>
</fileset>
```

Khi một file bị loại ở FileSet, công cụ không nhận file đó làm đầu vào. Nó không thể báo lỗi hay cảnh báo về nội dung của file đó trong lần chạy này.

### 4.2. Phân tích file nhưng bỏ qua một số cảnh báo

Đôi khi file vẫn cần được phân tích, nhưng một cảnh báo cụ thể đã được chấp nhận tạm thời hoặc không thể sửa ngay vì lý do tương thích. Khi đó, dùng suppression/filter của chính công cụ.

Ví dụ, Checkstyle vẫn phân tích `LegacyAdapter.java`, nhưng bỏ qua rule `LineLength` trong file đó. Những rule khác trên cùng file vẫn được áp dụng.

Hai cách này có mức ảnh hưởng khác nhau. Loại cả file làm mất toàn bộ tín hiệu chất lượng của file; suppression theo rule giữ lại các kiểm tra còn lại. Nên chọn phạm vi hẹp nhất đáp ứng lý do miễn trừ.

## 5. Khai báo đường dẫn chất lượng trong Ant bằng property

Đầu tiên, định nghĩa các đường dẫn chung ở đầu `build.xml`:

```xml
<property name="src.main.dir" location="src/main/java"/>
<property name="src.test.dir" location="src/test/java"/>

<property name="quality.config.dir" location="config/quality"/>
<property name="quality.tools.dir" location="lib/quality-tools"/>
<property name="quality.report.dir" location="build/reports/quality"/>

<property name="checkstyle.config"
          location="${quality.config.dir}/checkstyle/checkstyle.xml"/>
<property name="checkstyle.properties"
          location="${quality.config.dir}/checkstyle/checkstyle.properties"/>
<property name="checkstyle.report"
          location="${quality.report.dir}/checkstyle/checkstyle-result.xml"/>
```

Những property này giúp:

- Thay đổi vị trí cấu hình mà không phải sửa từng task.
- Tạo output report dưới cùng một thư mục gốc.
- Dùng chung đường dẫn khi gọi công cụ từ nhiều target.
- Dễ truyền biến thể cấu hình bằng property nếu dự án có profile khác nhau.

Tạo thư mục báo cáo trước khi chạy tool:

```xml
<target name="prepare-quality-reports">
    <mkdir dir="${quality.report.dir}/checkstyle"/>
    <mkdir dir="${quality.report.dir}/pmd"/>
    <mkdir dir="${quality.report.dir}/spotbugs"/>
</target>
```

Task `mkdir` tạo cả các thư mục cha chưa tồn tại. Không cần tạo sẵn thư mục report trong source control.

## 6. Ví dụ cụ thể với Checkstyle

Checkstyle là công cụ kiểm tra quy ước và cấu trúc mã Java, chẳng hạn cách đặt tên, import, dấu ngoặc, độ dài dòng hoặc những quy tắc về style. Ant không tự tích hợp mọi công cụ chất lượng mã trong core; muốn gọi Checkstyle bằng task `<checkstyle>`, cần cung cấp task adapter và các thư viện mà phiên bản Checkstyle đang dùng yêu cầu.

### 6.1. Cấu hình task trong Ant

Ví dụ khi các JAR Checkstyle và dependency của nó được quản lý trong thư mục `lib/quality-tools/checkstyle`:

```xml
<path id="checkstyle.tool.classpath">
    <fileset dir="${quality.tools.dir}/checkstyle" includes="*.jar"/>
</path>

<taskdef resource="com/puppycrawl/tools/checkstyle/ant/checkstyle-ant-task.properties"
         classpathref="checkstyle.tool.classpath"/>
```

`taskdef` đăng ký task để Ant hiểu phần tử `<checkstyle>`. Classpath ở đây là classpath để Ant nạp công cụ, khác với FileSet các file Java mà Checkstyle sẽ phân tích.

Nếu dự án dùng một bản phân phối Checkstyle khác, cách cung cấp task và dependency có thể khác. Hãy dùng đúng hướng dẫn của phiên bản đã chọn, đồng thời cố định phiên bản tool trong build để máy lập trình và CI chạy cùng hành vi.

### 6.2. File cấu hình Checkstyle riêng

Tạo `config/quality/checkstyle/checkstyle.xml`:

```xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">

<module name="Checker">
    <property name="charset" value="UTF-8"/>
    <property name="severity" value="warning"/>

    <module name="FileTabCharacter"/>

    <module name="LineLength">
        <property name="fileExtensions" value="java"/>
        <property name="max" value="120"/>
    </module>

    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
        <module name="UnusedImports"/>
        <module name="NeedBraces"/>
        <module name="MethodName"/>
    </module>

    <module name="SuppressionFilter">
        <property name="file" value="${config_loc}/suppressions.xml"/>
    </module>
</module>
```

File này mô tả những quy tắc Checkstyle phải áp dụng. Ví dụ:

- `charset` chỉ định encoding của source.
- `severity` đặt mức độ mặc định cho vi phạm.
- `FileTabCharacter` kiểm tra ký tự tab theo cấu hình của rule.
- `LineLength` giới hạn độ dài dòng.
- Các module trong `TreeWalker` kiểm tra cấu trúc cây cú pháp Java.
- `SuppressionFilter` nạp file suppression riêng.

Tên và tham số rule có thể thay đổi giữa các phiên bản Checkstyle. Khi nâng cấp tool, cần đối chiếu cấu hình với tài liệu của phiên bản mới; một module đã bị đổi tên hoặc xóa có thể khiến công cụ không đọc được config.

### 6.3. Property cho vị trí file cấu hình phụ

Trong `config/quality/checkstyle/checkstyle.properties`:

```properties
config_loc=config/quality/checkstyle
```

Task Checkstyle nhận file property này để mở rộng `${config_loc}` trong cấu hình:

```xml
<checkstyle config="${checkstyle.config}"
            properties="${checkstyle.properties}"
            failOnViolation="true">
    ...
</checkstyle>
```

Khi dùng cấu hình thực tế, hãy xác nhận cách phiên bản Checkstyle Ant task xử lý thuộc tính `properties` và đường dẫn tương đối. Có thể dùng đường dẫn tuyệt đối do Ant tạo từ `location` nếu cần tránh phụ thuộc thư mục làm việc hiện tại.

### 6.4. File suppression riêng

Tạo `config/quality/checkstyle/suppressions.xml`:

```xml
<?xml version="1.0"?>
<!DOCTYPE suppressions PUBLIC
    "-//Checkstyle//DTD SuppressionFilter Configuration 1.2//EN"
    "https://checkstyle.org/dtds/suppressions_1_2.dtd">

<suppressions>
    <!-- Chỉ miễn rule LineLength cho adapter cũ. -->
    <suppress files=".*[/\\]LegacyAdapter\.java"
              checks="LineLength"/>

    <!-- Bỏ qua các rule cho mã được sinh tự động. -->
    <suppress files=".*[/\\]generated[/\\].*"
              checks=".*"/>
</suppressions>
```

Suppression file cho phép mô tả ngoại lệ theo file, rule, dòng hoặc các điều kiện mà filter hỗ trợ. Ví dụ đầu tiên chỉ miễn `LineLength` cho `LegacyAdapter.java`; các rule khác vẫn kiểm tra file đó. Ví dụ thứ hai miễn các kiểm tra trong đường dẫn generated, nhưng trong thực tế có thể nên loại generated code ngay từ FileSet để tránh phân tích toàn bộ.

Không nên dùng suppression quá rộng như `checks=".*"` cho cả thư mục source chính nếu không có lý do rõ ràng. Mỗi ngoại lệ nên có phạm vi nhỏ, có lý do và nếu cần thì có thời hạn xem xét lại.

### 6.5. Target Checkstyle và báo cáo riêng

```xml
<target name="checkstyle" depends="prepare-quality-reports">
    <checkstyle config="${checkstyle.config}"
                properties="${checkstyle.properties}"
                failOnViolation="true">
        <fileset dir="${src.main.dir}">
            <include name="**/*.java"/>
            <exclude name="**/generated/**"/>
            <exclude name="**/vendor/**"/>
        </fileset>

        <formatter type="xml" toFile="${checkstyle.report}"/>
    </checkstyle>
</target>
```

Target này thực hiện các việc:

1. Tạo thư mục report.
2. Chọn file Java trong source tree.
3. Loại generated code và vendor code khỏi phạm vi phân tích.
4. Đọc rule từ `checkstyle.xml` và suppression từ file riêng.
5. Ghi kết quả XML vào `build/reports/quality/checkstyle`.
6. Làm target/build thất bại khi phát hiện vi phạm theo cấu hình `failOnViolation`.

Đường dẫn report không nằm trong `src`; mỗi lần chạy có thể tạo lại file mà không làm bẩn source tree.

## 7. Loại trừ file bằng FileSet của Ant

FileSet là cách trực tiếp để xác định những file nào được chuyển cho một task. Các pattern `include` và `exclude` được khai báo ngay trong buildfile hoặc có thể được tổ chức thành property để dùng lại.

Ví dụ chỉ phân tích mã ứng dụng, bỏ qua mã sinh tự động và thư mục vendor:

```xml
<fileset dir="${src.main.dir}">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/vendor/**"/>
</fileset>
```

Nếu muốn bỏ qua test source trong target kiểm tra main, chỉ cần trỏ FileSet đến `src/main/java`. Nếu muốn phân tích test riêng, tạo một target và FileSet riêng cho `src/test/java`.

### 7.1. Lưu pattern loại trừ trong property

Với dự án có nhiều target, có thể dùng property để quản lý các đường dẫn chuẩn:

```xml
<property name="quality.exclude.generated" value="**/generated/**"/>
<property name="quality.exclude.vendor" value="**/vendor/**"/>
```

Sau đó tham chiếu:

```xml
<fileset dir="${src.main.dir}">
    <include name="**/*.java"/>
    <exclude name="${quality.exclude.generated}"/>
    <exclude name="${quality.exclude.vendor}"/>
</fileset>
```

Nếu danh sách pattern dài hoặc cần được chia sẻ giữa nhiều buildfile, có thể đưa chúng vào một file cấu hình riêng hoặc một resource collection được import phù hợp. Cần giữ cách tổ chức dễ truy vết để người review biết vì sao một nhánh source không được kiểm tra.

### 7.2. Không loại trừ quá rộng

Các pattern như `**/*` hoặc `**/service/**` có thể vô tình bỏ qua phần lớn mã quan trọng. Trước khi thêm exclusion, hãy xác định:

- File nào thật sự không thuộc quyền kiểm soát của nhóm?
- File có được sinh lại tự động hay không?
- Có thể sửa generator để mã sinh ra tuân thủ quy tắc không?
- Chỉ cần miễn một rule hay phải bỏ cả file khỏi phân tích?
- Ngoại lệ có cần ngày xem xét lại hoặc ticket theo dõi không?

Mục tiêu của exclusion là tránh cảnh báo không có giá trị, không phải làm giảm số cảnh báo bằng cách che mã nguồn đang cần cải thiện.

## 8. Tệp suppression của từng công cụ có định dạng riêng

Không có một file exclusion chung dùng được cho mọi công cụ. Checkstyle, PMD và SpotBugs có mô hình rule và cú pháp filter khác nhau.

| Công cụ | File cấu hình thường gặp | File loại trừ/miễn trừ thường gặp | Nội dung báo cáo |
|---|---|---|---|
| Checkstyle | `checkstyle.xml` | `suppressions.xml` hoặc filter được cấu hình trong Checkstyle | XML hoặc plain; có thể chuyển đổi để hiển thị HTML |
| PMD | `ruleset.xml` | Exclude pattern hoặc cấu hình suppression theo phiên bản PMD | XML, text hoặc định dạng report mà phiên bản PMD hỗ trợ |
| SpotBugs | Cấu hình phân tích và effort/threshold | `exclude-filter.xml` | XML, HTML hoặc định dạng do plugin hỗ trợ |

Các tên file trên là quy ước dễ hiểu, không phải tên bắt buộc. Cú pháp, vị trí khai báo và khả năng của từng công cụ phụ thuộc phiên bản. Không nên sao chép nội dung suppression của Checkstyle sang PMD hoặc SpotBugs vì mỗi công cụ diễn giải file theo schema riêng.

### 8.1. Ví dụ cấu trúc filter của SpotBugs

SpotBugs có thể dùng một filter XML để loại một số bug pattern trong phạm vi class hoặc package nhất định. Ví dụ minh họa dạng cấu trúc:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<FindBugsFilter>
    <Match>
        <Class name="com.acme.legacy.LegacyAdapter"/>
        <Bug pattern="EI_EXPOSE_REP"/>
    </Match>
</FindBugsFilter>
```

File này diễn đạt một ngoại lệ có phạm vi cụ thể: bỏ qua bug pattern `EI_EXPOSE_REP` đối với class `LegacyAdapter`. Khi dùng thật, cần xác nhận tên bug pattern, schema và cách truyền `excludeFilter` theo phiên bản SpotBugs Ant task đang cài.

### 8.2. Ví dụ cấu hình ruleset riêng cho PMD

PMD dùng ruleset XML để chọn rule và cấu hình tham số. Ví dụ minh họa một ruleset tối giản:

```xml
<?xml version="1.0"?>
<ruleset name="Project Quality Rules"
         xmlns="http://pmd.sourceforge.net/ruleset/2.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://pmd.sourceforge.net/ruleset/2.0.0
                             https://pmd.github.io/pmd-6.55.0/ruleset_2_0_0.xsd">
    <description>Rules used by this project.</description>

    <rule ref="category/java/bestpractices.xml"/>
    <rule ref="category/java/errorprone.xml"/>
</ruleset>
```

Đây là ví dụ về việc tách lựa chọn rule khỏi source. Đường dẫn category và schema phụ thuộc phiên bản PMD; khi nâng cấp PMD, hãy cập nhật theo cấu trúc ruleset của phiên bản mới. Việc chọn file Java nào để phân tích vẫn có thể được kiểm soát riêng từ FileSet hoặc cơ chế input của task PMD.

## 9. Tổ chức báo cáo ở ngoài source tree

Mỗi công cụ nên ghi báo cáo vào một thư mục con riêng:

```text
build/reports/quality/
├── checkstyle/
│   └── checkstyle-result.xml
├── pmd/
│   └── pmd-report.xml
└── spotbugs/
    └── spotbugs.html
```

Tách theo công cụ giúp:

- Không ghi đè report của công cụ khác.
- Dễ cấu hình artifact path trong CI.
- Dễ tìm báo cáo khi một bước thất bại.
- Có thể xóa toàn bộ báo cáo bằng một target clean.
- Có thể chạy lại riêng một công cụ mà không thay đổi source.

### 9.1. Tạo thư mục report

```xml
<target name="prepare-quality-reports">
    <mkdir dir="${quality.report.dir}/checkstyle"/>
    <mkdir dir="${quality.report.dir}/pmd"/>
    <mkdir dir="${quality.report.dir}/spotbugs"/>
</target>
```

### 9.2. Ghi report XML

Với Checkstyle:

```xml
<formatter type="xml"
           toFile="${quality.report.dir}/checkstyle/checkstyle-result.xml"/>
```

Với các công cụ khác, hãy dùng formatter hoặc thuộc tính output tương ứng của task/version đó. Không giả định tất cả task Ant dùng cùng một cú pháp `formatter`.

### 9.3. Chuyển XML sang HTML

Một số công cụ cung cấp report XML, sau đó có thể chuyển sang HTML bằng XSLT hoặc công cụ report tương thích. Ví dụ khái niệm:

```xml
<xslt in="${quality.report.dir}/checkstyle/checkstyle-result.xml"
      out="${quality.report.dir}/checkstyle/index.html"
      style="config/quality/checkstyle/checkstyle-noframes-sorted.xsl"/>
```

Task `xslt` cần stylesheet phù hợp với đúng cấu trúc XML của báo cáo. Không dùng stylesheet của phiên bản Checkstyle khác nếu schema report đã thay đổi. Có thể chọn một report viewer của CI thay vì tự chuyển HTML nếu nền tảng CI đã hỗ trợ định dạng XML đó.

## 10. Kết nối các bước chất lượng mã thành target Ant

Nên tạo target riêng cho từng công cụ để có thể chạy độc lập:

```xml
<target name="quality-checkstyle" depends="prepare-quality-reports">
    <!-- Gọi Checkstyle với config, suppressions và report riêng. -->
</target>

<target name="quality-pmd" depends="prepare-quality-reports">
    <!-- Gọi PMD với ruleset và report riêng. -->
</target>

<target name="quality-spotbugs" depends="compile,prepare-quality-reports">
    <!-- SpotBugs phân tích bytecode đã biên dịch. -->
</target>

<target name="quality" depends="quality-checkstyle,quality-pmd,quality-spotbugs"/>
```

Checkstyle và PMD có thể phân tích source trực tiếp theo cấu hình tương ứng; SpotBugs phân tích bytecode nên target thường cần phụ thuộc vào `compile`. Cấu hình cụ thể phụ thuộc task adapter và phiên bản công cụ đang dùng.

Lợi ích của cách chia target:

```bash
# Chỉ chạy quy tắc style
ant quality-checkstyle

# Chỉ chạy phân tích PMD
ant quality-pmd

# Chỉ chạy phân tích bytecode
ant quality-spotbugs

# Chạy tất cả kiểm tra chất lượng
ant quality
```

Khi một công cụ phát hiện lỗi, log cho biết target nào thất bại. Người phát triển có thể chạy lại đúng target thay vì chạy toàn bộ quy trình.

## 11. Đưa cấu hình chất lượng mã vào Git và CI

Các file cấu hình và suppression quyết định chính sách chất lượng của repository, vì vậy thường nên được commit:

```text
config/quality/checkstyle/checkstyle.xml
config/quality/checkstyle/suppressions.xml
config/quality/pmd/ruleset.xml
config/quality/spotbugs/exclude-filter.xml
```

Ngược lại, báo cáo và output sinh tự động thường không nên commit:

```gitignore
/build/
```

Nếu repository có một số file trong `build` cần giữ lại vì lý do đặc biệt, hãy dùng quy tắc ignore cụ thể hơn thay vì bỏ qua toàn bộ thư mục một cách máy móc.

Trong CI, pipeline có thể:

1. Checkout mã nguồn và cấu hình quality.
2. Cài hoặc lấy đúng phiên bản công cụ.
3. Chạy `ant quality`.
4. Thu thập các file trong `build/reports/quality/**` kể cả khi một bước kiểm tra thất bại, nếu nền tảng CI hỗ trợ thao tác luôn chạy.
5. Hiển thị báo cáo hoặc lưu chúng thành artifact của job.

Các report là bằng chứng của một lần chạy trên một revision cụ thể. Chúng có thể được lưu theo thời hạn của CI, nhưng không nên dùng report cũ như thể nó mô tả trạng thái source hiện tại.

### 11.1. Không để đường dẫn phụ thuộc máy cá nhân

Tránh cấu hình kiểu:

```xml
<property name="checkstyle.config"
          location="C:/Users/Alice/tools/project/checkstyle.xml"/>
```

Đường dẫn này chỉ đúng trên một máy. Thay vào đó, dùng đường dẫn tương đối với project basedir:

```xml
<property name="checkstyle.config"
          location="config/quality/checkstyle/checkstyle.xml"/>
```

Nếu tool JAR được cài bên ngoài repository, hãy lấy vị trí từ biến môi trường hoặc property CI và kiểm tra file tồn tại trước khi chạy task.

## 12. Kiểm soát việc build thất bại khi có vi phạm

Một công cụ chất lượng mã có thể hoạt động theo hai mục tiêu:

- Chỉ tạo báo cáo để nhóm xem và xử lý dần.
- Là cổng chất lượng: nếu vi phạm vượt ngưỡng hoặc có lỗi nghiêm trọng, build phải thất bại.

Với Checkstyle, `failOnViolation` có thể điều khiển việc task làm build thất bại khi phát hiện vi phạm. Ví dụ:

```xml
<checkstyle config="${checkstyle.config}"
            properties="${checkstyle.properties}"
            failOnViolation="true">
    <fileset dir="${src.main.dir}" includes="**/*.java"/>
    <formatter type="xml" toFile="${checkstyle.report}"/>
</checkstyle>
```

Khi muốn chạy thử mà chưa chặn build, có thể cấu hình chế độ báo cáo không fail nếu task/phiên bản hỗ trợ; tuy nhiên, CI chính thức cần có một tiêu chí rõ ràng để không vô tình bỏ qua vi phạm.

Không nên chỉ kiểm tra xem file report có tồn tại hay không. Một report rỗng hoặc một report được tạo thành công không đồng nghĩa source không có vi phạm. Cần xem trạng thái task, nội dung report và chính sách fail của target.

### 12.1. Tách bước phân tích và bước quyết định

Với một số quy trình, có thể chạy công cụ ở chế độ tạo report trước rồi để một bước khác áp dụng ngưỡng hoặc so sánh baseline. Cách này hữu ích khi nhóm đang giảm dần nợ kỹ thuật. Tuy nhiên, cần ghi rõ:

- Vi phạm mới nào sẽ làm build thất bại?
- Vi phạm cũ nào đang được miễn trừ?
- Ai có quyền thêm suppression?
- Khi nào suppression cần được xem xét lại?

Nếu không có chính sách, suppression có thể tăng dần và làm công cụ mất ý nghĩa.

## 13. Quản lý ngoại lệ có trách nhiệm

Một tệp suppression là một phần của chính sách chất lượng, không chỉ là nơi để làm cho build xanh. Khi thêm ngoại lệ, nên ghi lại lý do trong comment hoặc hệ thống theo dõi liên quan.

Ví dụ comment trong tài liệu ngoại lệ:

```xml
<!--
  LegacyAdapter giữ nguyên định dạng tương thích với giao thức cũ.
  Chỉ miễn LineLength; các quy tắc khác vẫn được áp dụng.
  Xem xét lại khi loại bỏ giao thức legacy.
-->
<suppress files=".*[/\\]LegacyAdapter\.java"
          checks="LineLength"/>
```

Các nguyên tắc hữu ích:

- Chỉ miễn đúng rule đang gây cảnh báo không thể xử lý ở thời điểm hiện tại.
- Giới hạn theo file, class, package, bug pattern hoặc dòng cụ thể nếu tool hỗ trợ.
- Không miễn toàn bộ source tree để xử lý một vài cảnh báo.
- Ghi lý do và liên kết ticket nếu ngoại lệ chỉ mang tính tạm thời.
- Review thay đổi suppression giống như review thay đổi code.
- Xóa ngoại lệ khi nguyên nhân đã được khắc phục.

## 14. Lỗi thường gặp khi tách cấu hình và báo cáo

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Ant không tìm thấy file config | Property hoặc đường dẫn tương đối sai | Kiểm tra basedir, property và file thực tế |
| Ant báo không nhận diện task quality | Chưa đăng ký taskdef hoặc thiếu JAR adapter | Kiểm tra taskdef resource và classpath của tool |
| Tool không đọc được config XML | Schema, tên rule hoặc property không phù hợp phiên bản | Đối chiếu tài liệu của phiên bản công cụ đang dùng |
| Suppression không có tác dụng | Regex file, tên rule hoặc đường dẫn không khớp | Kiểm tra cú pháp suppression và tên check thực tế trong report |
| Không thấy một số file trong report | FileSet include/exclude đã loại chúng trước khi phân tích | Kiểm tra phạm vi FileSet và source directory |
| Report không được tạo | Thư mục đích chưa tồn tại, formatter/output sai hoặc task dừng trước khi ghi | Tạo thư mục trước, kiểm tra log và cú pháp output của task |
| Report bị ghi đè bởi target khác | Nhiều task dùng cùng một file đích | Dùng thư mục và tên report riêng theo công cụ/lần chạy |
| Working tree xuất hiện nhiều report | Output đang được ghi vào source tree hoặc chưa ignore | Chuyển report vào `build/reports` và cập nhật `.gitignore` |
| CI chạy khác máy cá nhân | Phiên bản tool, JDK hoặc config khác nhau | Cố định version, lưu config trong Git và in thông tin môi trường |
| Không còn cảnh báo vì suppression quá rộng | File suppression đã miễn quá nhiều rule hoặc source | Thu hẹp pattern và kiểm tra phạm vi được miễn |

## 15. Một số lệnh và cách kiểm tra cấu hình

Trước khi chạy chất lượng mã, có thể xem target được khai báo:

```bash
ant -p
```

Chạy riêng Checkstyle:

```bash
ant quality-checkstyle
```

Chạy tất cả công cụ:

```bash
ant quality
```

Xóa report cũ cùng output build:

```bash
ant clean
```

Nếu muốn chỉ xóa report quality mà giữ lại class đã biên dịch, tạo target riêng:

```xml
<target name="clean-quality-reports">
    <delete dir="${quality.report.dir}"/>
</target>
```

Sau đó có thể chạy:

```bash
ant clean-quality-reports quality
```

Khi report có vấn đề, kiểm tra log target và đường dẫn thực tế. Có thể dùng `echo` để in property quan trọng:

```xml
<target name="show-quality-paths">
    <echo message="Quality config: ${quality.config.dir}"/>
    <echo message="Quality reports: ${quality.report.dir}"/>
    <echo message="Checkstyle config: ${checkstyle.config}"/>
</target>
```

Không in secret hoặc token vào log. Các đường dẫn cấu hình thường an toàn để hiển thị, nhưng property có thể chứa thông tin nhạy cảm nếu buildfile được thiết kế không cẩn thận.

## 16. Checklist tổ chức thư mục chất lượng mã

Trước khi đưa quy trình quality vào CI, có thể đối chiếu những điểm sau:

- File cấu hình của từng tool nằm trong một thư mục cấu hình riêng.
- File suppression/exclusion có định dạng riêng của công cụ tương ứng.
- Phân biệt loại cả file khỏi phân tích và chỉ miễn một rule trên file.
- Source FileSet có include/exclude rõ ràng.
- Báo cáo được ghi vào `build/reports/quality/<tool>`.
- Thư mục report được tạo trước khi tool chạy.
- Task adapter và dependency của tool được cố định theo phiên bản.
- Target riêng cho từng công cụ và target tổng hợp được khai báo rõ.
- CI thu thập report sau khi chạy, kể cả khi quality gate thất bại nếu nền tảng hỗ trợ.
- Report sinh tự động không bị commit nhầm vào source tree.
- Suppression có phạm vi hẹp, lý do rõ và được review.
- Đường dẫn không phụ thuộc tên người dùng hoặc thư mục cài tool trên máy cá nhân.

## 17. Kết luận

Với Apache Ant, nên tổ chức cấu hình chất lượng mã thành ba nhóm độc lập: file cấu hình quy tắc, file loại trừ/miễn trừ và báo cáo được sinh ra. Cấu hình và suppression được lưu trong một thư mục như `config/quality`; source FileSet xác định file nào được phân tích; báo cáo được ghi vào `build/reports/quality` để CI thu thập và có thể tái tạo.

Điểm quan trọng là phân biệt loại toàn bộ file khỏi phạm vi phân tích với việc chỉ miễn một cảnh báo cụ thể. FileSet `exclude` phù hợp khi một nhóm file không thuộc phạm vi kiểm tra; suppression của từng công cụ phù hợp khi file vẫn cần được phân tích nhưng một rule cụ thể có ngoại lệ. Khi các đường dẫn, target và report được cấu hình tập trung, quy trình chất lượng mã trở nên minh bạch, dễ review và nhất quán giữa máy phát triển với CI.

## Tài liệu tham khảo

- [Apache Ant — Path-like Structures](https://ant.apache.org/manual/using.html#path)
- [Apache Ant — FileSet Type](https://ant.apache.org/manual/Types/fileset.html)
- [Checkstyle — Ant Task](https://checkstyle.org/anttask.html)
- [Checkstyle — SuppressionFilter](https://checkstyle.org/filters/suppressionfilter.html)
- [PMD — Rule Sets](https://docs.pmd-code.org/latest/pmd_userdocs_making_rulesets.html)
- [SpotBugs — Filter Files](https://spotbugs.readthedocs.io/en/stable/filter.html)
