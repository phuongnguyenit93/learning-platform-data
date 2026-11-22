# Phụ thuộc bắc cầu, loại trừ và xử lý xung đột phiên bản với Ivy

Một thư viện Java thường phụ thuộc vào những thư viện khác. Khi ứng dụng khai báo thư viện A, Ivy có thể đọc metadata của A để tìm thư viện B mà A cần, rồi tiếp tục tìm các thư viện mà B cần. Những dependency được tìm thấy qua một hoặc nhiều bước như vậy được gọi là **phụ thuộc bắc cầu** (*transitive dependencies*).

Phụ thuộc bắc cầu giúp build file chỉ cần khai báo các thư viện mà ứng dụng sử dụng trực tiếp. Tuy nhiên, một dependency graph có thể đưa cùng một module vào nhiều lần với các revision khác nhau, hoặc kéo theo một thư viện mà ứng dụng không muốn sử dụng. Apache Ivy cung cấp ba nhóm cơ chế để kiểm soát tình huống này:

- Quyết định có đi theo dependency bắc cầu hay không.
- Loại trừ dependency không cần thiết bằng `exclude`.
- Giải quyết nhiều revision của cùng một module bằng conflict manager.

## 1. Dependency trực tiếp và dependency bắc cầu

Giả sử ứng dụng `billing-app` khai báo hai thư viện trực tiếp:

```text
billing-app
├── report-engine 3.2
│   └── xml-parser 1.4
└── storage-client 2.1
    └── xml-parser 2.0
```

`report-engine` và `storage-client` là dependency trực tiếp của ứng dụng. `xml-parser` là dependency bắc cầu vì ứng dụng không khai báo nó trực tiếp; hai thư viện phía trên đưa nó vào graph.

Trong Ivy, metadata của module được lấy từ repository. Metadata có thể là file `ivy.xml` của thư viện hoặc metadata tương thích do resolver đọc, chẳng hạn POM của repository Maven. Ivy dùng metadata đó để lần theo các dependency tiếp theo. Vì vậy, kết quả resolve phụ thuộc cả descriptor của ứng dụng lẫn metadata của các module trong repository.

Một descriptor đơn giản có thể khai báo như sau:

```xml
<ivy-module version="2.0">
    <info organisation="com.example" module="billing-app"/>

    <configurations>
        <conf name="compile"/>
        <conf name="runtime" extends="compile"/>
    </configurations>

    <dependencies>
        <dependency org="org.example" name="report-engine"
                    rev="3.2" conf="runtime->default"/>
        <dependency org="org.example" name="storage-client"
                    rev="2.1" conf="runtime->default"/>
    </dependencies>
</ivy-module>
```

Trong `conf="runtime->default"`, `runtime` là configuration của module hiện tại và `default` là configuration được chọn từ dependency. Configuration mapping giúp giới hạn dependency nào được dùng cho compile, runtime hoặc các mục đích khác. Một dependency chỉ xuất hiện trong kết quả của configuration đang resolve nếu mapping và metadata của nó cho phép.

Mặc định, dependency của một module được xét tiếp theo cách bắc cầu. Có thể tắt hành vi đó cho một dependency cụ thể bằng `transitive="false"`:

```xml
<dependency org="org.example" name="report-engine"
            rev="3.2"
            conf="runtime->default"
            transitive="false"/>
```

Khi đó Ivy lấy dependency được khai báo trực tiếp này nhưng không tiếp tục lấy các dependency bắc cầu do nó khai báo. Thuộc tính này có phạm vi trên dependency tương ứng, không phải lệnh tắt bắc cầu cho toàn bộ module. Nếu một thư viện bắc cầu vẫn được một dependency khác đưa vào graph, nó vẫn có thể xuất hiện trong kết quả resolve.

Chỉ nên dùng `transitive="false"` khi đã hiểu những thư viện phụ mà ứng dụng cần tự khai báo. Nếu `report-engine` cần `xml-parser` để hoạt động mà ta tắt bắc cầu, ứng dụng phải tự bổ sung dependency phù hợp; nếu không, lỗi có thể chỉ xuất hiện khi chạy chương trình.

## 2. Loại trừ dependency bằng `exclude`

Đôi khi ứng dụng không muốn nhận một dependency bắc cầu: thư viện đó đã được thay thế, không được phép sử dụng, gây xung đột hoặc không cần cho chức năng đang triển khai. Ivy cho phép đặt `exclude` bên trong một dependency để loại module khớp điều kiện khỏi nhánh dependency đó.

Ví dụ, `report-engine` đưa `xml-parser` vào graph nhưng ứng dụng đã chọn một parser khác tương thích:

```xml
<dependencies>
    <dependency org="org.example" name="report-engine"
                rev="3.2" conf="runtime->default">
        <exclude org="org.example.parser" module="xml-parser"/>
    </dependency>

    <dependency org="org.example" name="storage-client"
                rev="2.1" conf="runtime->default"/>

    <dependency org="org.example.parser" name="xml-parser"
                rev="2.0" conf="runtime->default"/>
</dependencies>
```

`exclude` nằm trong dependency `report-engine`, vì vậy nó thể hiện quyết định loại parser khỏi nhánh bắc cầu của dependency này. Dependency `xml-parser` được khai báo trực tiếp ở cuối vẫn là một đường vào graph riêng. Điều đó hữu ích khi ta muốn ngăn một nhánh đưa revision cũ vào, nhưng vẫn chủ động chọn revision mà ứng dụng sử dụng.

Các thuộc tính `org` và `module` xác định module cần loại trừ. Có thể bổ sung điều kiện theo artifact, loại artifact hoặc configuration khi cần phạm vi hẹp hơn. Việc dùng wildcard hay pattern phụ thuộc matcher được cấu hình trong Ivy; khi cần khớp chính xác một module, hãy dùng đầy đủ `org` và `module` cụ thể.

### Loại trừ ở cấp toàn bộ danh sách dependency

Nếu muốn áp dụng cùng một quy tắc cho tất cả dependency được khai báo trong descriptor của ứng dụng, có thể đặt `exclude` trực tiếp bên trong `<dependencies>`:

```xml
<dependencies>
    <exclude org="org.legacy" module="old-xml-api"/>

    <dependency org="org.example" name="report-engine"
                rev="3.2" conf="runtime->default"/>
    <dependency org="org.example" name="storage-client"
                rev="2.1" conf="runtime->default"/>
</dependencies>
```

Đây là quy tắc loại trừ chung của descriptor, thay vì chỉ gắn với một dependency cụ thể. Chọn phạm vi theo ý định: exclude lồng trong dependency khi chỉ một nhánh cần bỏ module; exclude ở cấp `<dependencies>` khi module đó phải bị loại khỏi các nhánh dependency của ứng dụng.

### Phân biệt `exclude` và `transitive="false"`

Hai cơ chế này đều có thể làm graph nhỏ đi nhưng tác động rất khác nhau:

| Cơ chế | Phạm vi | Hệ quả |
|---|---|---|
| `transitive="false"` | Một dependency được khai báo | Không lấy toàn bộ dependency bắc cầu của module đó |
| `<exclude .../>` lồng trong dependency | Một nhánh dependency | Chỉ loại module khớp điều kiện khỏi nhánh đó |
| `<exclude .../>` trực tiếp trong `<dependencies>` | Các nhánh dependency của descriptor hiện tại | Áp dụng quy tắc loại trừ chung |

Nếu chỉ có một thư viện không mong muốn, `exclude` thường diễn đạt chính xác hơn. Nếu không muốn Ivy đi theo bất kỳ dependency bắc cầu nào của một thư viện, `transitive="false"` phù hợp hơn, nhưng đòi hỏi ứng dụng tự quản lý các dependency cần thiết.

Không nên thêm exclude chỉ để làm mất một cảnh báo xung đột. Nếu thư viện bị loại vẫn là dependency bắt buộc của một thành phần khác, ứng dụng có thể gặp `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` hoặc lỗi tương tự lúc chạy. Trước khi loại trừ, cần biết module nào đang yêu cầu nó và phiên bản thay thế có tương thích hay không.

## 3. Xung đột phiên bản trong dependency graph

Một **version conflict** xuất hiện khi cùng một module — được nhận diện bởi cặp `organisation` và `module` — được yêu cầu ở nhiều revision khác nhau trong cùng dependency graph.

Tiếp tục ví dụ ban đầu:

```text
billing-app
├── report-engine 3.2
│   └── xml-parser 1.4
└── storage-client 2.1
    └── xml-parser 2.0
```

Ivy nhìn thấy `org.example.parser:xml-parser` ở cả revision `1.4` và `2.0`. Nếu không có quy tắc xử lý xung đột phù hợp, graph không thể được dùng như thể cả hai revision là cùng một module đơn nhất trên classpath. Conflict manager quyết định revision nào được giữ hoặc có nên dừng resolve.

Trong default settings, Ivy thường sử dụng conflict manager `latest-revision`. Manager này chọn revision mới nhất theo latest strategy được cấu hình. Vì vậy, với ví dụ trên, revision `2.0` thường được chọn. Tuy nhiên, “mới nhất” là kết quả của quy tắc so sánh revision trong Ivy, không phải cam kết rằng API của revision mới tương thích ngược với mọi thư viện đang dùng revision cũ.

Các module bị thay thế trong graph có thể được thể hiện là *evicted* trong báo cáo resolve. Khi đọc report, hãy phân biệt dependency được chọn với dependency đã bị loại do conflict manager.

## 4. Các conflict manager thường gặp

Conflict manager quy định cách Ivy xử lý khi một module xuất hiện ở nhiều revision. Một số lựa chọn tiêu biểu:

| Manager | Cách xử lý | Khi cân nhắc sử dụng |
|---|---|---|
| `latest-revision` | Chọn revision mới nhất theo latest strategy | Khi chính sách dự án chấp nhận revision mới nhất trong conflict set |
| `latest-time` | Chọn revision có thời điểm xuất bản mới nhất | Khi metadata thời gian xuất bản là tiêu chí mong muốn |
| `latest-compatible` | Chọn revision mới nhất được xem là tương thích với các revision trong conflict | Khi cần một lựa chọn dung hòa theo chiến lược tương thích |
| `strict` | Báo lỗi khi phát hiện xung đột | Khi muốn buộc nhóm phát triển giải quyết version conflict một cách tường minh |
| `all` | Giữ tất cả revision thay vì chọn một revision duy nhất | Chỉ khi hệ thống thực sự cần và có thể cô lập nhiều revision |

`latest-revision` tiện dụng nhưng có thể che giấu một thay đổi không tương thích. `strict` hữu ích trong CI vì build dừng ngay khi graph có hai revision của cùng module, buộc người phát triển chọn một chính sách rõ ràng. `all` không phải lựa chọn an toàn mặc định cho một classpath ứng dụng thông thường: nhiều JAR có thể chứa cùng class, khiến kết quả nạp class phụ thuộc thứ tự classpath và gây lỗi khó chẩn đoán.

## 5. Chỉ định conflict manager trong descriptor

Có thể đặt quy tắc cho một module cụ thể bằng phần tử `<conflict>` trong phần `<dependencies>` của `ivy.xml`:

```xml
<ivy-module version="2.0">
    <info organisation="com.example" module="billing-app"/>

    <configurations>
        <conf name="runtime"/>
    </configurations>

    <dependencies>
        <dependency org="org.example" name="report-engine"
                    rev="3.2" conf="runtime->default"/>
        <dependency org="org.example" name="storage-client"
                    rev="2.1" conf="runtime->default"/>

        <conflict org="org.example.parser"
                 module="xml-parser"
                 manager="strict"/>
    </dependencies>
</ivy-module>
```

Khi `xml-parser` xuất hiện ở nhiều revision, quy tắc `strict` khiến resolve thất bại để nhóm phát triển xử lý conflict. Phần tử `<conflict>` gắn chính sách với module được nhận diện bởi `org` và `module`; nó không tự chọn một revision mới hay thay đổi metadata của các thư viện phụ thuộc.

Conflict manager cần được đăng ký trong Ivy settings. Các manager chuẩn thường có sẵn trong default settings; nếu dự án định nghĩa manager riêng hoặc dùng settings tối giản, hãy khai báo manager tương ứng trong `ivysettings.xml`:

```xml
<ivysettings>
    <conflict-managers>
        <conflict-manager name="strict"
                          class="org.apache.ivy.plugins.conflict.StrictConflictManager"/>
    </conflict-managers>
</ivysettings>
```

Trong build file Ant, nạp settings trước khi resolve:

```xml
<project name="billing-build"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <target name="resolve">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:resolve file="ivy.xml" conf="runtime"/>
    </target>
</project>
```

Nếu không cần chính sách riêng cho từng module, dự án cũng có thể cấu hình default conflict manager trong settings. Khi đổi default manager, cần xem xét tác động tới toàn bộ dependency graph được resolve bằng settings đó.

## 6. Resolve, report và retrieve trong Ant

Ivy cung cấp Ant tasks để phân giải dependency graph, tạo báo cáo và đưa artifact đã resolve vào thư mục build. Ivy Ant tasks cần có Ivy JAR trong classpath của Ant, đồng thời build file khai báo namespace `antlib:org.apache.ivy.ant`.

```xml
<project name="billing-build"
         default="prepare-runtime"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="build.dir" location="build"/>

    <target name="prepare-runtime">
        <ivy:settings file="ivysettings.xml"/>

        <!-- Đọc ivy.xml và giải quyết graph của configuration runtime. -->
        <ivy:resolve file="ivy.xml" conf="runtime"/>

        <!-- Tạo báo cáo để xem dependency được chọn và dependency bị evict. -->
        <ivy:report todir="${build.dir}/ivy-report" conf="runtime"/>

        <!-- Sao chép artifact đã resolve vào thư mục thư viện của build. -->
        <ivy:retrieve conf="runtime"
                      pattern="${build.dir}/lib/[artifact]-[revision].[ext]"/>
    </target>
</project>
```

Vai trò của từng task:

- `ivy:settings` nạp cấu hình resolver, cache và conflict manager từ settings file.
- `ivy:resolve` đọc descriptor, truy vấn metadata repository và giải quyết dependency graph cho configuration được chọn.
- `ivy:report` tạo báo cáo để quan sát graph, revision được chọn và dependency bị evict.
- `ivy:retrieve` sao chép các artifact đã resolve theo pattern vào thư mục dự án.

Resolve và retrieve là hai công đoạn khác nhau. Một module có thể resolve thành công nhưng artifact chưa được sao chép vào thư mục mà task Java hoặc compiler đang dùng. Hãy bảo đảm `conf` của retrieve trùng với configuration cần đóng gói và pattern tạo ra đường dẫn mà classpath tham chiếu.

Nếu muốn dùng trực tiếp các artifact trong Ivy cache mà không sao chép chúng, có thể tạo Ant path từ configuration đã resolve:

```xml
<target name="compile">
    <ivy:resolve file="ivy.xml" conf="compile"/>
    <ivy:cachepath conf="compile" pathid="compile.dependencies"/>

    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.dependencies"/>
    </javac>
</target>
```

`ivy:cachepath` tạo path tham chiếu đến artifact trong cache cho configuration được chọn. Dùng `ivy:retrieve` khi cần một thư mục dependency có thể kiểm tra hoặc đóng gói cùng build; dùng `ivy:cachepath` khi task Ant có thể tham chiếu trực tiếp các file trong cache.

## 7. Quy trình xử lý một version conflict

Khi Ivy báo có nhiều revision của cùng module, nên xử lý theo thứ tự có thể kiểm chứng:

1. **Xác định module bị conflict.** Dùng cặp `org` và `module` trong thông báo hoặc report. Không chỉ nhìn tên JAR vì nhiều module có thể tạo artifact tên gần giống nhau.
2. **Tìm các nhánh đưa module vào graph.** Xem dependency trực tiếp nào kéo theo revision thứ nhất và dependency nào kéo theo revision còn lại.
3. **Xác định ứng dụng thực sự cần gì.** Kiểm tra API mà các thư viện đang dùng, yêu cầu phiên bản tối thiểu và các thay đổi tương thích trong release notes của thư viện.
4. **Chọn biện pháp có phạm vi nhỏ nhất.** Nếu một nhánh kéo theo dependency không cần thiết, dùng `exclude` tại nhánh đó. Nếu toàn bộ dependency bắc cầu của một thư viện không được dùng, cân nhắc `transitive="false"` và khai báo rõ các thư viện còn cần.
5. **Chọn chính sách phiên bản.** Nếu các nhánh tương thích với một revision chung, điều chỉnh dependency trực tiếp hoặc conflict manager để graph chọn revision đó. Nếu cần buộc nhóm giải quyết conflict thay vì tự động chọn, dùng `strict` cho module liên quan.
6. **Resolve lại và đọc report.** Xác nhận revision cuối cùng, các dependency bị evict và artifact được retrieve. Không chỉ dựa vào việc task `resolve` kết thúc thành công.
7. **Chạy kiểm thử ứng dụng.** Kiểm tra compile và runtime, đặc biệt các đường code gọi API của module vừa đổi revision. Một graph hợp lệ không chứng minh các thư viện nhị phân tương thích với nhau.

Không nên dùng `exclude` để che mọi conflict, cũng không nên luôn chọn revision cao nhất mà không kiểm tra tương thích. Nếu hai thư viện yêu cầu các API không tương thích, việc ép một revision vào classpath có thể chuyển lỗi từ giai đoạn resolve sang compile hoặc runtime.

## 8. Những lỗi thường gặp

1. **Nghĩ rằng chỉ dependency trực tiếp mới được tải.** Ivy có thể lấy metadata và tiếp tục resolve dependency bắc cầu. Hãy kiểm tra graph và configuration thay vì chỉ đếm số dòng `<dependency>` trong `ivy.xml`.
2. **Tắt bắc cầu quá rộng.** `transitive="false"` bỏ toàn bộ nhánh dependency của một module. Nếu chỉ muốn loại một thư viện, đặt `exclude` cụ thể hơn.
3. **Đặt exclude ở sai phạm vi.** Exclude lồng trong một dependency kiểm soát nhánh đó; quy tắc ở cấp `<dependencies>` dùng chung cho các nhánh của descriptor. Chọn đúng vị trí để không vô tình loại dependency cần thiết.
4. **Cho rằng exclude ở một nhánh loại module khỏi mọi nhánh.** Cùng module vẫn có thể đi vào graph qua dependency khác hoặc được khai báo trực tiếp. Kiểm tra tất cả đường đi trong report.
5. **Coi revision mới nhất là revision tương thích nhất.** `latest-revision` áp dụng latest strategy, không xác nhận binary compatibility. Đọc yêu cầu phiên bản và kiểm thử ứng dụng.
6. **Dùng `all` trên classpath thông thường.** Giữ nhiều revision của cùng module có thể gây trùng class và hành vi phụ thuộc thứ tự classpath. Chỉ dùng khi có chủ đích cô lập và kiểm soát từng revision.
7. **Resolve một configuration nhưng retrieve configuration khác.** Artifact được sao chép có thể thiếu hoặc không khớp classpath. Giữ nhất quán tên configuration ở `resolve`, `report`, `retrieve` hoặc `cachepath`.
8. **Resolve thành công nhưng không có JAR trong thư mục build.** `ivy:resolve` giải quyết graph; `ivy:retrieve` mới sao chép artifact theo pattern. Thêm bước retrieve nếu các task sau dùng thư mục đó.
9. **Không nạp đúng Ivy settings.** Resolver và conflict manager có thể khác với dự kiến nếu build không nạp `ivysettings.xml`. Nạp settings trước khi gọi resolve và kiểm tra report tạo ra.

## Tài liệu tham khảo

- [Apache Ivy — Dependency Element](https://ant.apache.org/ivy/history/latest-milestone/ivyfile/dependency.html): khai báo dependency, configuration mapping và thuộc tính `transitive`.
- [Apache Ivy — Exclude Element](https://ant.apache.org/ivy/history/latest-milestone/ivyfile/exclude.html): loại trừ dependency ở phạm vi module hoặc dependency.
- [Apache Ivy — Conflict Management](https://ant.apache.org/ivy/history/latest-milestone/concept.html#conflicts): khái niệm xung đột và cách Ivy chọn revision.
- [Apache Ivy — Conflict Manager](https://ant.apache.org/ivy/history/latest-milestone/settings/conflict-managers.html): các conflict manager và cấu hình manager.
- [Apache Ivy — Ant Tasks](https://ant.apache.org/ivy/history/latest-milestone/use/ant.html): tích hợp Ivy vào build file Apache Ant.
