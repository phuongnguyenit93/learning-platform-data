# Property cục bộ với `local` và phạm vi trong `sequential` hoặc macro

Trong Apache Ant, property thường được dùng để chia sẻ cấu hình giữa nhiều target, chẳng hạn thư mục nguồn, phiên bản thư viện hoặc thư mục đầu ra. Tuy nhiên, có những giá trị chỉ cần tồn tại trong một target, một khối thực thi tuần tự hoặc một lần gọi macro. Nếu mọi giá trị đều được đặt ở phạm vi toàn project, các target hoặc macro có thể vô tình dùng chung tên property và ảnh hưởng lẫn nhau.

Ant cung cấp task `<local>` để khai báo property cục bộ. Property này chỉ nhìn thấy trong phạm vi được khai báo, nhờ đó có thể dùng lại tên property trong các target, các khối `sequential` hoặc các lần gọi macro mà không làm rò rỉ giá trị ra phạm vi bên ngoài.

## 1. Property toàn project và property cục bộ

Thông thường, property được khai báo bằng task `<property>` ở cấp project:

```xml
<project name="local-property-demo" default="show" basedir=".">

    <property name="environment" value="production"/>

    <target name="show">
        <echo message="Environment: ${environment}"/>
    </target>

</project>
```

Property `environment` có thể được sử dụng ở các target trong project. Ant có quy tắc property bất biến: khi một property đã được đặt, một lần khai báo thông thường tiếp theo với cùng tên sẽ không thay đổi giá trị đã có.

Điều này hữu ích với cấu hình dùng chung, nhưng có thể gây khó khăn khi một target cần giá trị tạm thời cùng tên. Ví dụ, project đặt `environment=production`, trong khi target kiểm thử muốn dùng `environment=test`. Nếu chỉ gọi `<property>` lần nữa, giá trị toàn project đã được đặt sẽ không bị thay thế.

`<local>` tạo một phạm vi riêng cho property. Trong phạm vi đó, property cục bộ có thể che khuất property cùng tên ở phạm vi bên ngoài. Khi rời khỏi phạm vi cục bộ, giá trị bên ngoài lại được nhìn thấy.

## 2. Khai báo property cục bộ bằng `<local>`

Task `<local>` khai báo tên property sẽ có phạm vi cục bộ:

```xml
<target name="test">
    <local name="environment"/>
    <property name="environment" value="test"/>
    <echo message="Environment inside target: ${environment}"/>
</target>
```

`<local>` chỉ khai báo phạm vi và tên property; nó không tự gán giá trị. Sau khi khai báo, có thể dùng `<property>` để đặt giá trị cục bộ. Hãy khai báo local trước khi property được sử dụng hoặc được đặt trong phạm vi đó.

Ví dụ đầy đủ dưới đây cho thấy property cục bộ che khuất property toàn project trong target:

```xml
<project name="local-property-demo" default="demo" basedir=".">

    <property name="environment" value="production"/>

    <target name="demo">
        <local name="environment"/>
        <property name="environment" value="test"/>
        <echo message="Inside demo: ${environment}"/>
    </target>

    <target name="show-global">
        <echo message="Outside demo: ${environment}"/>
    </target>

</project>
```

Chạy hai target:

```sh
ant demo show-global
```

Trong target `demo`, Ant hiển thị `test`. Trong target `show-global`, Ant hiển thị `production`. Giá trị `test` chỉ tồn tại trong phạm vi của target `demo`; nó không sửa property toàn project.

Nếu bỏ `<local name="environment"/>`, lệnh `<property name="environment" value="test"/>` không thể ghi đè property `environment` đã được đặt ở cấp project. Khi đó target vẫn nhìn thấy `production`.

## 3. Phạm vi trong target

Khi `<local>` được khai báo trong một target, property cục bộ có hiệu lực trong target đó. Các target khác không nhìn thấy giá trị cục bộ này.

```xml
<project name="target-scope-demo" default="run" basedir=".">

    <property name="message" value="Project value"/>

    <target name="run">
        <local name="message"/>
        <property name="message" value="Value for run target"/>
        <echo message="run: ${message}"/>
    </target>

    <target name="another">
        <echo message="another: ${message}"/>
    </target>

</project>
```

Khi chạy:

```sh
ant run another
```

target `run` dùng giá trị `Value for run target`; target `another` dùng lại giá trị `Project value`. Vì vậy, target có thể dùng tên property quen thuộc mà không phải tạo một tên toàn project riêng cho từng giá trị tạm thời.

Nếu project không khai báo property toàn cục cùng tên, property cục bộ chỉ có thể được tham chiếu trong phạm vi local đã khai báo. Sau khi ra khỏi target, không có giá trị toàn cục thay thế; do đó không nên trông đợi target khác đọc được giá trị local.

## 4. Phạm vi trong phần tử `sequential`

`<sequential>` là một container task thực hiện các task con theo thứ tự. Nó thường được dùng bên trong `<parallel>` để gom các bước phải chạy lần lượt trong từng nhánh, hoặc xuất hiện trong phần thân của macro.

Khi khai báo `<local>` bên trong một khối `sequential`, property có phạm vi trong khối tuần tự đó. Điều này hữu ích khi nhiều nhánh tuần tự cần dùng cùng tên property nhưng giữ các giá trị riêng.

Ví dụ hai nhánh độc lập trong `<parallel>`:

```xml
<project name="sequential-local-demo" default="run" basedir=".">

    <target name="run">
        <parallel>
            <sequential>
                <local name="component"/>
                <property name="component" value="api"/>
                <echo message="Building ${component}"/>
            </sequential>

            <sequential>
                <local name="component"/>
                <property name="component" value="web"/>
                <echo message="Building ${component}"/>
            </sequential>
        </parallel>
    </target>

</project>
```

Hai nhánh đều sử dụng tên `component`, nhưng mỗi khối `sequential` có phạm vi local riêng. Nhánh thứ nhất in `Building api`, nhánh thứ hai in `Building web`. Các property cục bộ không ghi đè lẫn nhau và không tạo một property `component` dùng chung ở cấp project.

Điểm quan trọng là đặt `<local>` bên trong từng `sequential`, trước task đặt giá trị. Nếu khai báo một property local ở phạm vi bao ngoài rồi để nhiều nhánh dùng chung, giá trị đó thuộc phạm vi bao ngoài và không còn là hai giá trị riêng theo từng nhánh.

`<parallel>` có thể thực thi các nhánh đồng thời. Local property theo từng `sequential` giúp tránh va chạm tên property giữa những nhánh đó. Tuy nhiên, nó không tự làm cho các tệp đầu ra, thư mục hoặc tài nguyên dùng chung trở nên an toàn khi nhiều nhánh cùng ghi; các tài nguyên đó vẫn cần được tổ chức riêng hoặc đồng bộ thích hợp.

## 5. Phạm vi trong macro

Macro Ant cho phép định nghĩa một nhóm task có thể tái sử dụng với các thuộc tính đầu vào khác nhau. Nếu macro cần property trung gian, property đó nên có phạm vi trong lần gọi macro để những lần gọi liên tiếp không ảnh hưởng lẫn nhau.

Ví dụ khai báo macro `build-component`:

```xml
<project name="macro-local-demo" default="run" basedir=".">

    <macrodef name="build-component">
        <attribute name="component"/>
        <sequential>
            <local name="component.message"/>
            <property name="component.message"
                      value="Preparing @{component}"/>
            <echo message="${component.message}"/>
        </sequential>
    </macrodef>

    <target name="run">
        <build-component component="api"/>
        <build-component component="web"/>
    </target>

</project>
```

Trong ví dụ:

- `<macrodef>` định nghĩa macro `build-component`.
- `<attribute name="component"/>` khai báo thuộc tính đầu vào của macro.
- `@{component}` là cú pháp tham chiếu thuộc tính macro trong phần thân macro.
- `<local name="component.message"/>` khai báo property trung gian cục bộ.
- `${component.message}` đọc property sau khi nó được đặt.

Khi target `run` gọi macro với `component="api"`, macro tạo thông điệp `Preparing api`. Lần gọi tiếp theo với `component="web"` tạo thông điệp `Preparing web`. Property `component.message` thuộc phạm vi lần gọi macro, nên giá trị của hai lần gọi không xung đột.

Trong macro, cần phân biệt hai cú pháp:

| Cú pháp | Ý nghĩa |
|---|---|
| `@{component}` | Thay bằng giá trị attribute của macro invocation |
| `${component.message}` | Đọc property Ant trong phạm vi hiện hành |

Attribute macro không phải là property Ant. Nếu cần giữ một giá trị trung gian để nhiều task trong macro cùng dùng, có thể gán nó vào local property như ví dụ trên.

## 6. Kết hợp phạm vi cục bộ với property toàn project

Một cách dùng phổ biến là giữ các cấu hình chung ở cấp project và dùng local property cho giá trị tạm thời của từng target hoặc macro.

```xml
<project name="build-config-demo" default="run" basedir=".">

    <property name="build.dir" location="build"/>
    <property name="default.profile" value="production"/>

    <target name="run">
        <local name="profile"/>
        <property name="profile" value="test"/>
        <echo message="Profile: ${profile}"/>
        <echo message="Output: ${build.dir}"/>
    </target>

</project>
```

Ở đây, `build.dir` là property toàn project vì nhiều target có thể cùng cần thư mục đầu ra. `profile` chỉ là giá trị riêng của target `run`, vì vậy nó được khai báo bằng `<local>`.

Không nhất thiết phải khai báo local cho mọi property. Hãy dùng property toàn project khi nhiều phần của build cần cùng một cấu hình ổn định; dùng local khi giá trị chỉ có ý nghĩa trong một phạm vi thực thi cụ thể hoặc cần được cô lập giữa các lần gọi.

## 7. Quy tắc và giới hạn cần nhớ

- Task `<local>` có từ Apache Ant 1.8.0. Build dùng Ant cũ hơn có thể không nhận diện task này.
- `<local>` chỉ khai báo tên và phạm vi property; nó không nhận thuộc tính `value` để gán giá trị trực tiếp.
- Đặt `<local>` trước khi sử dụng hoặc đặt property trong phạm vi đó.
- Property cục bộ có thể che khuất property cùng tên ở phạm vi bên ngoài; khi rời phạm vi, property bên ngoài lại được nhìn thấy.
- Local property vẫn tuân theo nguyên tắc đặt giá trị một lần trong phạm vi của nó. Khai báo local không biến property thành biến có thể gán lại tùy ý.
- Không khai báo local ở vị trí tùy ý ngoài những phạm vi Ant hỗ trợ như target, sequential hoặc macrodef.
- Property cục bộ không phải biến Java hay biến shell; nó là property của Ant được giới hạn phạm vi theo cơ chế của Ant.

Ví dụ sau không hợp lệ về ý tưởng vì local chưa được khai báo trước khi sử dụng:

```xml
<target name="incorrect-order">
    <echo message="${temporary.value}"/>
    <local name="temporary.value"/>
    <property name="temporary.value" value="hello"/>
</target>
```

Hãy chuyển `<local>` lên trước:

```xml
<target name="correct-order">
    <local name="temporary.value"/>
    <property name="temporary.value" value="hello"/>
    <echo message="${temporary.value}"/>
</target>
```

## 8. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Giá trị local không thay thế property toàn project trong target | Chưa khai báo `<local>` trước khi đặt property | Thêm `<local name="..."/>` vào đúng phạm vi trước task đặt giá trị |
| Target khác vẫn thấy giá trị toàn project | Đang đọc property global sau khi target local đã kết thúc | Đây là hành vi đúng; local không ghi đè giá trị project bên ngoài |
| Property local không được tìm thấy | Đang tham chiếu nó ngoài target, sequential hoặc macro scope đã khai báo | Chuyển thao tác sử dụng vào đúng phạm vi hoặc truyền dữ liệu qua cơ chế phù hợp |
| Hai nhánh `sequential` ghi đè giá trị của nhau | Property được khai báo ở phạm vi bao ngoài thay vì từng nhánh | Khai báo cùng tên local riêng bên trong mỗi `sequential` |
| Các lần gọi macro dùng chung giá trị trung gian ngoài dự kiến | Property trung gian chưa được khai báo local trong macro | Khai báo local trong phần thân macro để cô lập từng lần gọi |
| Ant báo không nhận diện task `local` | Phiên bản Ant đang chạy cũ hơn 1.8.0 | Dùng phiên bản Ant hỗ trợ task local hoặc thiết kế lại tên property theo cách tương thích |
| Property local có giá trị cũ trong cùng phạm vi | Property đã được đặt trước đó trong cùng phạm vi | Kiểm tra thứ tự khai báo và tránh kỳ vọng local property có thể gán lại như biến thông thường |

## 9. Checklist khi sử dụng `<local>`

- [ ] Đã xác định property là cấu hình dùng chung hay giá trị tạm thời theo phạm vi.
- [ ] Đã khai báo `<local name="..."/>` bên trong target, sequential hoặc macro phù hợp.
- [ ] Khai báo local xuất hiện trước khi property được đặt hoặc sử dụng.
- [ ] Property cùng tên ở phạm vi ngoài được hiểu là giá trị riêng, có thể được local che khuất tạm thời.
- [ ] Mỗi nhánh `sequential` cần giá trị riêng đều khai báo local trong chính nhánh đó.
- [ ] Property trung gian của macro được khai báo local để các lần gọi độc lập.
- [ ] Môi trường chạy sử dụng Apache Ant 1.8.0 trở lên.

Khi dùng đúng phạm vi, `<local>` giúp buildfile tái sử dụng tên property một cách an toàn hơn. Target có thể giữ giá trị riêng, các nhánh `sequential` có thể cô lập dữ liệu của mình và macro có thể được gọi nhiều lần mà không để lại property trung gian ở cấp project.
