# PropertySet và lựa chọn nhóm property

Trong Apache Ant, `PropertySet` là datatype dùng để chọn một nhóm property đã tồn tại trong build. Thay vì truyền hoặc hiển thị từng property riêng lẻ, bạn có thể chọn theo tên, tiền tố, biểu thức chính quy hoặc nhóm property dựng sẵn, rồi dùng tập kết quả ở những task hỗ trợ `propertyset`.

PropertySet hữu ích khi một build file có nhiều cấu hình nhưng mỗi bước chỉ cần một phần trong số đó. Ví dụ, build cha có thể chuyển nhóm property `app.*` sang build con, hoặc task `<echoproperties>` chỉ in những property liên quan đến cấu hình build để hỗ trợ chẩn đoán.

## 1. PropertySet là gì?

Ant property lưu các giá trị cấu hình như tên ứng dụng, thư mục đầu ra, phiên bản, cờ build hoặc đường dẫn công cụ. Khi số lượng property tăng lên, việc chọn đúng các giá trị cần dùng trở nên quan trọng.

`<propertyset>` mô tả một tập hợp property được lựa chọn từ những property hiện có. Nó không phải task thực thi công việc và cũng không tự tạo ra property mới. PropertySet cung cấp một cách nhóm và lọc tên property để task nhận nó quyết định cách sử dụng tập hợp đó.

Ví dụ, giả sử build có các property:

```xml
<property name="app.name" value="inventory"/>
<property name="app.version" value="2.4.0"/>
<property name="build.dir" value="build"/>
<property name="build.profile" value="release"/>
<property name="database.url" value="jdbc:example://localhost/app"/>
```

Bạn có thể tạo một PropertySet chỉ chọn nhóm `app.*`:

```xml
<propertyset id="application.properties">
    <propertyref prefix="app."/>
</propertyset>
```

Tập hợp `application.properties` chọn `app.name` và `app.version`. Các property `build.dir`, `build.profile` và `database.url` không thuộc tập hợp này.

## 2. Khai báo PropertySet và PropertyRef

Một PropertySet được khai báo bằng phần tử `<propertyset>`. Các phần tử `<propertyref>` bên trong mô tả điều kiện chọn property.

Cấu trúc cơ bản:

```xml
<propertyset id="my.properties">
    <propertyref name="app.version"/>
    <propertyref prefix="build."/>
</propertyset>
```

Trong ví dụ, tập hợp chọn property có tên chính xác `app.version` và tất cả property có tên bắt đầu bằng `build.`.

Các `<propertyref>` trong cùng PropertySet được kết hợp để tạo tập hợp kết quả. Một property khớp nhiều điều kiện vẫn là một property trong tập hợp, không tạo ra nhiều bản sao.

### 2.1. Chọn một property bằng `name`

Thuộc tính `name` chọn một property có tên chính xác:

```xml
<propertyset id="release.version">
    <propertyref name="app.version"/>
</propertyset>
```

Tập hợp trên chỉ chọn property `app.version` nếu property đó đã tồn tại. Nếu tên không tồn tại, không có property nào được chọn bởi điều kiện này.

Chọn theo tên phù hợp khi task chỉ cần một vài property cụ thể và bạn muốn danh sách được kiểm soát rõ ràng.

### 2.2. Chọn theo tiền tố bằng `prefix`

Thuộc tính `prefix` chọn những property có tên bắt đầu bằng tiền tố được chỉ định:

```xml
<propertyset id="database.properties">
    <propertyref prefix="database."/>
</propertyset>
```

Nếu build có `database.url`, `database.user` và `database.timeout`, cả ba property được chọn. Property `app.name` không khớp với tiền tố `database.`.

Tiền tố nên có dấu chấm cuối khi tên property được tổ chức theo namespace dạng `database.url`, `database.user`. Việc dùng `database.` giúp tránh vô tình chọn những tên chỉ bắt đầu bằng chuỗi `database` nhưng thuộc một nhóm khác, chẳng hạn `databaseBackup.dir`.

### 2.3. Chọn theo biểu thức chính quy bằng `regex`

Thuộc tính `regex` chọn tên property khớp với biểu thức chính quy:

```xml
<propertyset id="version.properties">
    <propertyref regex="^app\..*version$"/>
</propertyset>
```

Biểu thức trên chọn tên bắt đầu bằng `app.`, theo sau là bất kỳ chuỗi ký tự nào và kết thúc bằng `version`, chẳng hạn `app.version` hoặc `app.client.version`.

`regex` phù hợp khi quy tắc chọn phức tạp hơn một tiền tố đơn giản. Biểu thức chính quy cần được viết đúng cú pháp mà Ant sử dụng cho việc so khớp tên property. Trong XML, dấu nháy của thuộc tính vẫn phải được giữ đúng; ký tự `\` trong ví dụ là một phần của biểu thức chính quy.

Không nên dùng regex quá rộng nếu tập hợp sẽ được chuyển sang build con hoặc ghi ra log. Một biểu thức như `.*` có thể chọn gần như toàn bộ property và làm lộ những cấu hình không liên quan.

### 2.4. Chọn nhóm dựng sẵn bằng `builtin`

`propertyref` cũng hỗ trợ thuộc tính `builtin` để chọn một nhóm property dựng sẵn của Ant. Các nhóm thường dùng gồm:

| Giá trị `builtin` | Nhóm property được chọn |
|---|---|
| `all` | Tất cả property hiện có |
| `system` | Các property hệ thống của Java |
| `commandline` | Các property được truyền qua dòng lệnh |
| `env` | Các property được nhập từ biến môi trường |

Ví dụ:

```xml
<propertyset id="system.properties">
    <propertyref builtin="system"/>
</propertyset>
```

Nếu trước đó build đã nhập biến môi trường bằng:

```xml
<property environment="env"/>
```

thì nhóm môi trường có thể được chọn bằng:

```xml
<propertyset id="environment.properties">
    <propertyref builtin="env"/>
</propertyset>
```

Nhóm dựng sẵn giúp tránh phải viết nhiều điều kiện chọn. Tuy nhiên, `all`, `system` hoặc `env` có thể chứa nhiều giá trị không cần thiết. Hãy chọn phạm vi nhỏ nhất đáp ứng mục tiêu của task.

## 3. Kết hợp nhiều điều kiện lựa chọn

Một PropertySet có thể chứa nhiều `propertyref`. Điều này cho phép chọn một số property riêng lẻ và đồng thời chọn các nhóm theo tiền tố hoặc regex.

Ví dụ:

```xml
<propertyset id="build.configuration">
    <propertyref name="app.version"/>
    <propertyref prefix="build."/>
    <propertyref regex="^feature\..*"/>
</propertyset>
```

Tập hợp trên bao gồm:

- Property có tên chính xác `app.version`.
- Mọi property có tên bắt đầu bằng `build.`.
- Mọi property có tên bắt đầu bằng `feature.`.

Các điều kiện được kết hợp theo phép hợp: một property được chọn nếu nó khớp với ít nhất một `propertyref`. Đây là cách tạo allowlist theo nhiều nhóm cấu hình.

### 3.1. Phủ định bằng `negate`

Thuộc tính `negate="true"` đảo ngược kết quả lựa chọn: PropertySet chứa các property không được chọn bởi những điều kiện đã khai báo.

Ví dụ:

```xml
<propertyset id="properties-except-debug" negate="true">
    <propertyref prefix="debug."/>
</propertyset>
```

Tập hợp này chọn các property không thuộc nhóm `debug.`. `negate` hữu ích khi cần loại trừ một nhóm khỏi tập hợp lớn.

Hãy cẩn thận khi dùng phủ định để chuyển property sang build con hoặc in log. Khi dự án thêm property mới, property đó có thể tự động lọt vào tập hợp phủ định dù chưa được xem xét. Với dữ liệu nhạy cảm hoặc giao tiếp giữa các build, một allowlist cụ thể thường an toàn và dễ kiểm soát hơn.

### 3.2. Kết hợp các PropertySet lồng nhau

PropertySet có thể tham chiếu hoặc lồng một tập hợp khác để tái sử dụng quy tắc lựa chọn:

```xml
<propertyset id="application.properties">
    <propertyref prefix="app."/>
</propertyset>

<propertyset id="release.properties">
    <propertyset refid="application.properties"/>
    <propertyref prefix="release."/>
</propertyset>
```

`release.properties` kết hợp các property trong `application.properties` với những property có tiền tố `release.`. Khi quy tắc chọn của nhóm ứng dụng thay đổi, tập hợp tham chiếu có thể được tái sử dụng ở những vị trí khác.

Thuộc tính `refid` tham chiếu một datatype đã được khai báo bằng `id`. Đảm bảo ID tồn tại và thuộc đúng loại trước khi tham chiếu. Không khai báo các tập hợp lồng tham chiếu vòng lẫn nhau vì cấu trúc như vậy không tạo được một lựa chọn hữu ích.

## 4. Sử dụng PropertySet với task Ant

PropertySet chỉ có tác dụng tại những vị trí mà task hỗ trợ datatype này. Hai ví dụ phổ biến là `<echoproperties>` để hiển thị một nhóm property và task `<ant>` để truyền một nhóm property sang build con.

### 4.1. Hiển thị một nhóm property bằng `echoproperties`

Task `<echoproperties>` có thể nhận nested `<propertyset>`. Ví dụ:

```xml
<project name="propertyset-demo" default="show-app-properties">

    <property name="app.name" value="inventory"/>
    <property name="app.version" value="2.4.0"/>
    <property name="build.dir" value="build"/>
    <property name="build.profile" value="release"/>

    <propertyset id="application.properties">
        <propertyref prefix="app."/>
    </propertyset>

    <target name="show-app-properties">
        <echoproperties>
            <propertyset refid="application.properties"/>
        </echoproperties>
    </target>

</project>
```

Khi chạy:

```bash
ant show-app-properties
```

Ant chỉ hiển thị những property thuộc nhóm `app.` thông qua PropertySet đã khai báo. Property `build.dir` và `build.profile` không được chọn bởi tập hợp này.

`echoproperties` hữu ích khi cần chẩn đoán cấu hình, nhưng đầu ra vẫn có thể chứa thông tin nội bộ. Tránh đưa password, token hoặc thông tin kết nối nhạy cảm vào nhóm được in.

### 4.2. Truyền property sang build con bằng task `ant`

Khi một build file gọi build file khác bằng task `<ant>`, nested `<propertyset>` cho phép chọn property được chuyển sang project con.

Ví dụ build cha:

```xml
<project name="parent-build" default="run-child" basedir=".">

    <property name="app.name" value="inventory"/>
    <property name="app.version" value="2.4.0"/>
    <property name="build.dir" value="build"/>
    <property name="internal.debug" value="true"/>

    <propertyset id="child.application.properties">
        <propertyref prefix="app."/>
    </propertyset>

    <target name="run-child">
        <ant antfile="child-build.xml" target="show-config"
             inheritAll="false">
            <propertyset refid="child.application.properties"/>
        </ant>
    </target>

</project>
```

Build con `child-build.xml`:

```xml
<project name="child-build" default="show-config">
    <target name="show-config">
        <echo message="Application: ${app.name}"/>
        <echo message="Version: ${app.version}"/>
    </target>
</project>
```

Build cha chọn `app.name` và `app.version` rồi chuyển chúng cho build con. `build.dir` và `internal.debug` không được chọn bởi PropertySet. Thuộc tính `inheritAll="false"` hạn chế việc tự động kế thừa toàn bộ property thông thường của project cha; các property được truyền tường minh bằng nested `propertyset` vẫn được cung cấp cho project con. Các user property có quy tắc kế thừa riêng của task Ant.

Ví dụ này thể hiện lợi ích của PropertySet: build con nhận đúng nhóm cấu hình cần thiết mà không phải phụ thuộc vào mọi property nội bộ của build cha.

### 4.3. Không phải task nào cũng nhận PropertySet

PropertySet là datatype, không phải cú pháp có thể đặt tùy ý vào mọi phần tử Ant. Task phải công bố hỗ trợ nested `propertyset` thì cấu trúc đó mới hợp lệ.

Ví dụ, task `<exec>` thường nhận các phần tử `<env>` để đặt biến cho tiến trình con; không thể giả định rằng có thể đặt một `<propertyset>` trực tiếp vào `<exec>`. Hãy đọc tài liệu của task cụ thể trước khi thêm nested element.

## 5. Thay đổi tên property bằng mapper

Trong một số tình huống, build con cần cùng giá trị nhưng dùng namespace tên khác. PropertySet hỗ trợ nested mapper để ánh xạ tên property được chọn.

Ví dụ, đổi tiền tố `legacy.` thành `app.`:

```xml
<propertyset id="mapped.application.properties">
    <propertyref prefix="legacy."/>
    <mapper type="glob" from="legacy.*" to="app.*"/>
</propertyset>
```

Nếu có property `legacy.name=inventory`, mapper tạo tên đích `app.name` cho property được ánh xạ. Giá trị được giữ nguyên, còn tên property được chuyển theo quy tắc mapper.

Mapper hữu ích khi tích hợp build file cũ với một quy ước tên mới hoặc khi build con mong đợi namespace khác. Cần chọn mapper phù hợp với mẫu tên thực tế và tránh để nhiều property ánh xạ thành cùng một tên đích ngoài ý muốn.

## 6. Thời điểm đánh giá PropertySet

PropertySet có thuộc tính `dynamic` để điều khiển thời điểm đánh giá tập hợp. Mặc định `dynamic="true"`, nghĩa là các điều kiện lựa chọn được đánh giá khi tập hợp được sử dụng. Nếu đặt `dynamic="false"`, tập hợp được đánh giá khi nó được tạo.

Ví dụ:

```xml
<propertyset id="dynamic.properties" dynamic="true">
    <propertyref prefix="app."/>
</propertyset>

<propertyset id="snapshot.properties" dynamic="false">
    <propertyref prefix="app."/>
</propertyset>
```

Với tập hợp động, những property phù hợp được thêm sau thời điểm khai báo vẫn có thể được chọn khi tập hợp được dùng. Với tập hợp không động, kết quả lựa chọn được cố định tại thời điểm tạo tập hợp.

Hãy chọn theo cách property được thiết lập trong build:

- Dùng mặc định `dynamic="true"` khi property có thể được khai báo sau PropertySet nhưng trước lúc task sử dụng nó.
- Dùng `dynamic="false"` khi muốn cố định nhóm tên được chọn ngay tại thời điểm khai báo.

`dynamic` điều khiển thời điểm đánh giá lựa chọn; nó không làm cho Ant property trở thành mutable và cũng không cho phép ghi đè giá trị của property đã thiết lập.

## 7. Phân biệt PropertySet với các cơ chế property khác

Ant có nhiều cơ chế liên quan đến property, nhưng mỗi cơ chế giải quyết một việc khác nhau:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| `<property>` | Khai báo hoặc nạp giá trị property | `<property name="app.version" value="2.4.0"/>` |
| `<property environment="env"/>` | Nhập biến môi trường thành property có prefix | `${env.JAVA_HOME}` |
| `<propertyset>` | Chọn một nhóm property đã tồn tại | `<propertyref prefix="app."/>` |
| `<propertyfile>` | Đọc/ghi dữ liệu dạng properties trong tệp theo chức năng của task | Cập nhật file cấu hình phiên bản |
| `<filterset>` | Khai báo các bộ lọc token khi sao chép hoặc xử lý tệp bằng task hỗ trợ | Thay `@VERSION@` trong tài nguyên |

PropertySet không thay thế `<property>`: nó không phải cơ chế khai báo giá trị. Nó cũng không giống `filterset`, vì filterset thay thế token trong nội dung tệp còn PropertySet chọn các property để truyền hoặc sử dụng.

## 8. Lựa chọn PropertySet an toàn và dễ bảo trì

Khi chọn property, hãy bắt đầu từ nhu cầu của task nhận tập hợp:

- Nếu task chỉ cần vài giá trị đã biết, dùng `name` để chọn tường minh.
- Nếu các property được tổ chức theo namespace, dùng `prefix`.
- Nếu quy tắc tên có cấu trúc phức tạp, dùng `regex` và giữ biểu thức dễ đọc.
- Nếu thật sự cần một nhóm dựng sẵn, cân nhắc `builtin` và kiểm tra phạm vi property được chọn.
- Nếu cần loại trừ, dùng `negate` với hiểu biết rõ về các property có thể được thêm trong tương lai.
- Nếu cần chuyển tên sang namespace khác, dùng mapper và kiểm tra ánh xạ đích.

Với cấu hình nhạy cảm, nên chọn allowlist bằng các tên hoặc prefix cụ thể. Đừng chuyển tất cả property chỉ vì build con hiện tại chưa dùng hết; property mới được thêm vào build cha trong tương lai có thể vô tình bị chuyển theo.

Nếu PropertySet được dùng để ghi log, chỉ chọn những property được phép hiển thị. Một nhóm có tiền tố `database.` hoặc `deploy.` có thể chứa thông tin xác thực tùy cách dự án đặt tên; tên prefix không đảm bảo giá trị bên trong không nhạy cảm.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| PropertySet không chọn property mong muốn | Tên, prefix hoặc regex không khớp tên property thực tế | Kiểm tra chính xác tên property và quy tắc so khớp |
| Tập hợp rỗng | Property chưa được khai báo hoặc chưa được nạp khi tập hợp được đánh giá | Kiểm tra thứ tự khai báo và thuộc tính `dynamic` |
| Không nhận diện `refid` | ID chưa được khai báo hoặc tham chiếu sai tên | Khai báo PropertySet có `id` trước khi dùng và kiểm tra chính tả |
| Nested `propertyset` không được hỗ trợ | Task nhận nó không hỗ trợ datatype này hoặc đặt sai vị trí | Kiểm tra tài liệu task và chỉ đặt nested element tại vị trí được hỗ trợ |
| Regex chọn quá nhiều property | Mẫu biểu thức quá rộng | Giới hạn biểu thức theo namespace và hậu tố cần chọn |
| Build con nhận nhiều property ngoài dự kiến | Dùng `builtin="all"`, `negate` hoặc prefix quá rộng | Chuyển sang allowlist, xem lại `inheritAll` và phạm vi truyền property |
| Giá trị property không thay đổi dù khai báo lại | Ant property dùng quy tắc first definition wins | Kiểm tra nguồn và thứ tự thiết lập property; không xem PropertySet là cơ chế ghi đè |
| Log vô tình chứa thông tin bí mật | PropertySet chọn cả property nhạy cảm và được đưa vào `echoproperties` | Thu hẹp tập hợp, loại bỏ secret và không in toàn bộ môi trường |

## 10. Ví dụ tổng hợp: chuyển cấu hình có chọn lọc sang build con

Ví dụ sau minh họa cách tổ chức property theo namespace, chọn nhóm cần thiết và truyền chúng sang build con:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="parent" default="invoke-child" basedir=".">

    <property name="app.name" value="inventory"/>
    <property name="app.version" value="2.4.0"/>
    <property name="build.profile" value="release"/>
    <property name="build.output" value="build/dist"/>
    <property name="internal.debug" value="false"/>

    <propertyset id="application.config">
        <propertyref prefix="app."/>
        <propertyref name="build.profile"/>
    </propertyset>

    <target name="invoke-child">
        <ant antfile="child-build.xml" target="show-config"
             inheritAll="false">
            <propertyset refid="application.config"/>
        </ant>
    </target>

</project>
```

Build con:

```xml
<project name="child" default="show-config">
    <target name="show-config">
        <echo message="Application: ${app.name}"/>
        <echo message="Version: ${app.version}"/>
        <echo message="Profile: ${build.profile}"/>
    </target>
</project>
```

PropertySet `application.config` chọn hai property thuộc `app.` và property `build.profile`. Nó không chọn `build.output` hoặc `internal.debug`. Task `<ant>` chuyển đúng tập hợp đã chọn sang build con. Build con có thể sử dụng các property được chuyển mà không cần biết build cha đã khai báo những property nội bộ nào khác.

Để thử nghiệm, đặt hai file build cạnh nhau trong một thư mục, sau đó chạy:

```bash
ant invoke-child
```

Ant chạy target `invoke-child`, gọi build con và in ba giá trị cấu hình. Nếu đổi tên property ở build cha hoặc build con, hãy cập nhật quy tắc chọn và các tham chiếu tương ứng.

## 11. Checklist sử dụng PropertySet

- [ ] Các property cần chọn đã được khai báo hoặc nạp trước khi PropertySet được sử dụng.
- [ ] Đã chọn đúng phương thức `name`, `prefix`, `regex` hoặc `builtin`.
- [ ] Các điều kiện chọn trong cùng tập hợp phản ánh đúng nhóm property cần dùng.
- [ ] Đã cân nhắc `negate` và phạm vi property mới có thể xuất hiện trong tương lai.
- [ ] Các PropertySet lồng và `refid` tham chiếu đúng ID.
- [ ] Chỉ dùng nested PropertySet trong task có hỗ trợ datatype này.
- [ ] Đã cấu hình `dynamic` phù hợp với thời điểm property được thiết lập.
- [ ] Nếu dùng mapper, đã kiểm tra tên đích và tránh trùng lặp ngoài ý muốn.
- [ ] Khi gọi build con, đã xác định rõ property nào cần truyền và cách kế thừa property.
- [ ] Không đưa secret hoặc cấu hình nhạy cảm vào log hay tập hợp truyền không cần thiết.

PropertySet giúp build file Ant quản lý các nhóm cấu hình có chủ đích. Khi tổ chức property theo namespace, chọn bằng `propertyref` và sử dụng tập hợp ở task phù hợp, bạn có thể giảm việc truyền cấu hình dư thừa, tái sử dụng quy tắc lựa chọn và giữ ranh giới rõ ràng giữa các build.
