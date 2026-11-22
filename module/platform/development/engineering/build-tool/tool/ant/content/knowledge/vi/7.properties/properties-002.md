# Tính bất biến thông thường và nguyên tắc giá trị được đặt trước

## 1. Property trong Ant là gì?

Apache Ant dùng property để lưu các giá trị cấu hình của một lần build. Một property có tên và một giá trị dạng chuỗi, ví dụ:

```text
build.profile=development
app.version=1.4.0
output.dir=build/development
```

Trong build file, property được tham chiếu bằng cú pháp `${property.name}`:

```xml
<project name="sample" default="show-config">
    <property name="build.profile" value="development"/>
    <property name="app.version" value="1.4.0"/>

    <target name="show-config">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Version: ${app.version}"/>
    </target>
</project>
```

Khi chạy `ant show-config`, Ant thay các biểu thức property bằng giá trị đã được thiết lập. Property thường dùng để xác định profile, phiên bản artifact, thư mục đầu ra, đường dẫn công cụ, tùy chọn kiểm thử hoặc thông tin môi trường.

Điểm khác biệt quan trọng của property Ant là **một property thông thường chỉ được đặt giá trị một lần trong phạm vi của nó**. Khi tên đó đã có giá trị, lần đặt tiếp theo bằng cơ chế property thông thường sẽ không thay đổi giá trị cũ.

Quy tắc này thường được gọi là *first value wins* (giá trị được đặt trước sẽ được giữ lại).

## 2. Nguyên tắc giá trị được đặt trước

Xét ví dụ:

```xml
<project name="property-demo" default="show">
    <property name="build.profile" value="development"/>
    <property name="build.profile" value="production"/>

    <target name="show">
        <echo message="Profile: ${build.profile}"/>
    </target>
</project>
```

Kết quả là:

```text
Profile: development
```

Task `<property>` đầu tiên đã đặt `build.profile` thành `development`. Task thứ hai gặp cùng tên property nên không ghi đè được giá trị đã tồn tại. Ant không báo lỗi chỉ vì lần đặt thứ hai bị bỏ qua.

Quy tắc này áp dụng cho property thông thường được đặt bằng các cách như:

- `<property name="..." value="..."/>`.
- `<property file="..."/>` hoặc `<property url="..."/>`.
- Nạp property từ resource hoặc môi trường bằng task property.
- Các property được Ant cung cấp từ môi trường Java và thông tin của Ant.

Nếu một nguồn đã đặt tên property, nguồn được xử lý sau không thể thay giá trị đó bằng một lần đặt property thông thường.

### "Được đặt trước" là trước theo thời điểm thực thi

Không nên hiểu quy tắc này chỉ là dòng nào xuất hiện trước trong file XML. Điều cần xét là **lần gán thành công đầu tiên trong quá trình Ant thực thi build**.

Các phần tử cấu hình ở cấp project được xử lý khi Ant đọc build file. Task nằm bên trong target chỉ chạy khi target đó được thực hiện. Vì vậy, một property đặt ở cấp project có thể tồn tại trước khi bất kỳ target nào bắt đầu.

Ví dụ:

```xml
<project name="property-order" default="release">
    <property name="release.channel" value="development"/>

    <target name="release">
        <property name="release.channel" value="production"/>
        <echo message="Channel: ${release.channel}"/>
    </target>
</project>
```

Khi chạy target `release`, property ở cấp project đã được đặt trong lúc đọc build file. Task trong target không thể đổi nó thành `production`. Kết quả vẫn là `development`.

## 3. Thứ tự target và quan hệ depends

Khi property được đặt bên trong target, thứ tự chạy target quyết định target nào đặt giá trị trước.

Ví dụ:

```xml
<project name="property-order" default="release">
    <target name="defaults">
        <property name="artifact.suffix" value="-dev"/>
        <echo message="Defaults target: ${artifact.suffix}"/>
    </target>

    <target name="release" depends="defaults">
        <property name="artifact.suffix" value="-release"/>
        <echo message="Release target: ${artifact.suffix}"/>
    </target>
</project>
```

Khi chạy `ant release`:

1. Ant thực hiện target `defaults` vì `release` phụ thuộc vào target này.
2. `defaults` đặt `artifact.suffix` thành `-dev`.
3. Ant tiếp tục target `release`.
4. Task property trong `release` không thể thay giá trị đã có.
5. Cả hai dòng echo đều hiển thị `-dev`.

Kết quả:

```text
Defaults target: -dev
Release target: -dev
```

Nếu muốn `release` có cấu hình riêng, không nên cố ghi đè cùng một property. Hãy thiết kế các property có mục đích khác nhau:

```xml
<project name="property-order" default="release">
    <target name="defaults">
        <property name="development.suffix" value="-dev"/>
    </target>

    <target name="release">
        <property name="release.suffix" value="-release"/>
        <echo message="Development: ${development.suffix}"/>
        <echo message="Release: ${release.suffix}"/>
    </target>
</project>
```

Kết quả là hai giá trị cùng tồn tại, mỗi giá trị có ý nghĩa và phạm vi sử dụng rõ ràng.

Với những target độc lập, hãy khai báo quan hệ `depends` khi một target cần giá trị do target khác thiết lập. Không nên dựa vào thứ tự tình cờ của các target trong file để tạo ra một cấu hình mà build thực tế không bảo đảm.

## 4. Property mặc định và property truyền từ bên ngoài

Tính bất biến cho phép Ant kết hợp cấu hình mặc định với cấu hình do người chạy build cung cấp.

### Giá trị mặc định trong build file

```xml
<project name="sample" default="show">
    <property name="build.profile" value="local"/>
    <property name="output.dir" location="build/${build.profile}"/>

    <target name="show">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Output: ${output.dir}"/>
    </target>
</project>
```

Khi không truyền cấu hình, Ant dùng `local` và thư mục `build/local`. Đây là cách khai báo giá trị mặc định để build có thể chạy ngay trong môi trường phát triển.

### Ghi đè mặc định bằng -D

Người chạy có thể truyền user property trên command line:

```bash
ant -Dbuild.profile=ci show
```

Property `build.profile` đã được cung cấp trước khi build file đặt giá trị mặc định. Do đó, task `<property>` trong file không thể thay nó bằng `local`.

Kết quả:

```text
Profile: ci
Output: build/ci
```

Đây là cơ chế ghi đè mặc định được hỗ trợ có chủ đích. Người chạy chọn giá trị trước khi build bắt đầu; các task trong build sử dụng giá trị đó.

User property từ command line có mức ưu tiên cao hơn property thông thường được đặt trong build file. Một task `<property>` không thể sửa user property này.

### Kết hợp property file và giá trị mặc định

Có thể nạp file cấu hình trước, sau đó khai báo giá trị mặc định:

```xml
<project name="sample" default="show">
    <property file="config/build.properties"/>
    <property name="build.profile" value="local"/>
    <property name="output.dir" location="build/${build.profile}"/>

    <target name="show">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Output: ${output.dir}"/>
    </target>
</project>
```

Nếu `config/build.properties` chứa:

```properties
build.profile=ci
output.dir=build/ci
```

thì hai giá trị trong file được giữ lại. Nếu file không khai báo `build.profile`, task property phía sau mới đặt giá trị mặc định `local`.

Thứ tự ngược lại sẽ cho kết quả khác:

```xml
<project name="sample" default="show">
    <property name="build.profile" value="local"/>
    <property file="config/build.properties"/>

    <target name="show">
        <echo message="Profile: ${build.profile}"/>
    </target>
</project>
```

Trong trường hợp này, `build.profile` đã được đặt thành `local` trước khi file được nạp. Nếu file khai báo `build.profile=ci`, giá trị `local` vẫn được giữ lại.

Vì vậy, khi dùng property file như nguồn cấu hình có thể ghi đè mặc định, hãy nạp file trước các task đặt giá trị mặc định.

## 5. Property được nội suy tại thời điểm đặt giá trị

Property trong Ant không phải biến liên kết động. Khi một giá trị được tạo từ property khác, biểu thức được thay thế theo các giá trị đang có tại thời điểm property đó được đặt.

Ví dụ:

```xml
<project name="property-expansion" default="show">
    <property name="build.profile" value="development"/>
    <property name="output.dir" value="build/${build.profile}"/>
    <property name="build.profile" value="production"/>

    <target name="show">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Output: ${output.dir}"/>
    </target>
</project>
```

Kết quả:

```text
Profile: development
Output: build/development
```

Có hai điều xảy ra:

- Lần đặt thứ hai của `build.profile` bị bỏ qua, nên profile vẫn là `development`.
- `output.dir` đã được tạo từ `build.profile` tại thời điểm profile là `development`. Giá trị này không phải một công thức được đánh giá lại mỗi khi profile thay đổi.

Điều này cũng giải thích vì sao chỉ truyền một property đầu vào mới không tự cập nhật mọi property dẫn xuất đã được thiết lập trước đó.

Ví dụ, nếu file cấu hình đã đặt cả `build.profile` và `output.dir`, việc truyền `-Dbuild.profile=release` không tự tính lại `output.dir`. Nếu muốn đường dẫn theo profile, hãy để property file chỉ cung cấp profile và để build file tính giá trị mặc định của đường dẫn, hoặc truyền trực tiếp đường dẫn mong muốn.

## 6. Những nguồn property thường gặp và cách chúng tương tác

Ant có thể nhận property từ nhiều nguồn. Điều quan trọng là xác định nguồn nào đã đặt tên property trước khi một nguồn khác cố gắng đặt lại.

| Nguồn | Cách sử dụng | Đặc điểm |
|---|---|---|
| Command line | `ant -Dname=value target` | Tạo user property, ưu tiên hơn giá trị mặc định trong build file |
| Property file | `<property file="config.properties"/>` hoặc `-propertyfile` | Nạp một tập property; giá trị đã tồn tại không bị thay |
| Build file | `<property name="name" value="value"/>` | Thường dùng để khai báo mặc định |
| System properties | Được JVM cung cấp cho Ant | Có sẵn trong môi trường Java của tiến trình Ant |
| Environment | `<property environment="env"/>` | Nạp biến môi trường với tiền tố được chỉ định, ví dụ `env.PATH` |

Một ví dụ kết hợp:

```xml
<project name="sample" default="show">
    <property environment="env"/>
    <property file="config/build.properties"/>
    <property name="build.profile" value="local"/>
    <property name="build.owner" value="unknown"/>

    <target name="show">
        <echo message="Profile: ${build.profile}"/>
        <echo message="Owner: ${build.owner}"/>
        <echo message="PATH: ${env.PATH}"/>
        <echo message="Java: ${java.version}"/>
    </target>
</project>
```

Trong ví dụ này:

- Biến môi trường được nạp thành các property có tiền tố `env.`.
- File cấu hình được nạp trước các giá trị mặc định.
- `build.profile` và `build.owner` chỉ được đặt nếu chưa có giá trị từ nguồn trước.
- `java.version` là property hệ thống do JVM cung cấp và được Ant công bố cho build.

Không nên suy ra một thứ tự ưu tiên chung giữa mọi nguồn chỉ từ bảng này. Với mỗi tên property, hãy xét nguồn nào đã đặt nó và loại property được tạo ra. Đặc biệt, user property trên command line có ưu tiên cao hơn giá trị mặc định mà build file đặt.

## 7. Vì sao Ant chọn tính bất biến?

Tính bất biến giúp build có hành vi dễ dự đoán. Khi một cấu hình đã được xác định, các task tiếp theo có thể sử dụng cùng giá trị mà không lo một target khác âm thầm thay đổi nó.

Các lợi ích chính gồm:

- **Tính nhất quán:** nhiều target cùng đọc một property sẽ nhận cùng một giá trị trong lần build.
- **Dễ truy vết:** khi kiểm tra log hoặc cấu hình, có thể tìm nguồn đã đặt giá trị đầu tiên.
- **Giảm phụ thuộc vào thứ tự ngẫu nhiên:** một target không thể vô tình thay cấu hình chung do target khác đặt.
- **Hỗ trợ giá trị mặc định:** build file có thể cung cấp mặc định mà không ghi đè cấu hình đã được truyền từ bên ngoài.
- **Dễ tái lập:** cùng một bộ property đầu vào sẽ tạo ra cùng cấu hình cho các task sử dụng chúng, miễn là các đầu vào khác cũng ổn định.

Đổi lại, người viết build phải thiết kế luồng cấu hình ngay từ đầu. Nếu cần một giá trị thay đổi theo giai đoạn, hãy đặt tên riêng cho từng giai đoạn hoặc tách thành các lần gọi build với đầu vào khác nhau.

## 8. Cách xử lý khi thật sự cần giá trị thay đổi

Nếu build cần các giá trị khác nhau ở các giai đoạn, hãy chọn cách biểu diễn phù hợp thay vì cố ghi đè một property thông thường.

### Dùng các tên property riêng biệt

```xml
<project name="sample" default="show">
    <property name="compile.output.dir" value="build/classes"/>
    <property name="package.output.dir" value="build/package"/>
    <property name="release.output.dir" value="build/release"/>

    <target name="show">
        <echo message="Compile: ${compile.output.dir}"/>
        <echo message="Package: ${package.output.dir}"/>
        <echo message="Release: ${release.output.dir}"/>
    </target>
</project>
```

Mỗi property mô tả một giá trị khác nhau, nên không cần ghi đè.

### Dùng cấu hình đầu vào cho từng lần chạy

Nếu cần chạy cùng một build cho nhiều môi trường, truyền giá trị khác nhau khi gọi Ant:

```bash
ant -Dbuild.profile=development package
ant -Dbuild.profile=staging package
ant -Dbuild.profile=production package
```

Mỗi lần gọi là một tiến trình build với bộ property đầu vào riêng. Đây là cách đơn giản để tách cấu hình giữa các môi trường.

### Dùng cơ chế có phạm vi riêng

Ant có hỗ trợ property cục bộ trong các phiên bản hiện đại thông qua task `<local>`. Cơ chế này giúp giới hạn khả năng nhìn thấy property trong một target hoặc một khối thực thi, hữu ích khi macro hoặc target được gọi nhiều lần với dữ liệu riêng.

Phạm vi cục bộ không nên bị nhầm với một biến có thể thay đổi tùy ý. Vẫn cần thiết kế thời điểm đặt property và nơi đọc nó. Nếu thực sự cần biến có thể gán lại, phải dùng một task hoặc extension chuyên dụng; ví dụ `<var>` của Ant-Contrib không thuộc Ant core và cần được cài đặt riêng. Chỉ nên dùng biến mutable khi bài toán thực sự cần trạng thái thay đổi trong một lần chạy.

## 9. Lỗi thường gặp

### Đặt property lần thứ hai nhưng giá trị không thay đổi

Đây là hành vi chuẩn. Tìm lần đặt đầu tiên của tên property, bao gồm command line, property file, phần cấu hình cấp project và các target dependency đã chạy trước.

### Target sau không thể thay giá trị do target trước đặt

Kiểm tra quan hệ `depends` và thứ tự thực thi. Nếu hai target cần hai giá trị khác nhau, hãy dùng hai tên property hoặc tách cấu hình theo lần chạy.

### File cấu hình không ghi đè được giá trị mặc định

Có thể build file đã đặt property trước khi nạp file. Hãy nạp property file trước task khai báo mặc định, rồi kiểm tra xem tên property có khớp chính xác không.

### Property dẫn xuất vẫn giữ đường dẫn cũ

Giá trị dẫn xuất đã được nội suy tại thời điểm nó được đặt. Đặt lại property đầu vào không làm giá trị dẫn xuất được tính lại. Hãy sắp xếp thứ tự nạp cấu hình, hoặc truyền giá trị cuối cùng một cách tường minh.

### Nhầm property của Ant với system property của JVM

`ant -Dname=value` là tùy chọn của Ant, tạo user property cho build. `-Dname=value` trong `ANT_OPTS` là tùy chọn JVM, tạo system property cho tiến trình chạy Ant. Hai cách có thể cùng xuất hiện trong tập property mà build đọc được nhưng được xử lý ở những tầng khác nhau.

### Tên property không khớp

Tên property được so sánh theo chuỗi. `build.profile`, `Build.profile` và `build_profile` là các tên khác nhau. Dùng một quy ước đặt tên nhất quán và kiểm tra đúng chính tả khi tham chiếu.

## 10. Nguyên tắc thiết kế

- Khai báo giá trị mặc định ở cấp project hoặc tại target chuyên trách cấu hình.
- Nạp property file trước các giá trị mặc định nếu muốn file có thể cung cấp cấu hình.
- Dùng `-Dname=value` cho những giá trị cần chọn theo từng lần chạy.
- Dùng `depends` để thể hiện rõ target nào phải đặt property trước target nào sử dụng nó.
- Không dựa vào việc một task `<property>` có thể ghi đè property đã tồn tại.
- Tránh tạo property dẫn xuất trước khi các property đầu vào đã được nạp đầy đủ.
- Dùng tên riêng cho các giá trị thuộc các giai đoạn hoặc mục đích khác nhau.
- Khi cần thay đổi cấu hình giữa các môi trường, ưu tiên nhiều property file hoặc nhiều lần gọi Ant với bộ đầu vào riêng.
- Chỉ dùng extension mutable khi thật sự cần trạng thái thay đổi và nhóm hiểu rõ tác động của extension đó.

Tính bất biến của property là quy tắc nền tảng trong cách Ant quản lý cấu hình: lần đặt thành công đầu tiên xác định giá trị mà các task tiếp theo nhìn thấy. Khi nắm được thứ tự nạp property, thứ tự thực thi target và thời điểm nội suy, bạn có thể xây dựng cấu hình có mặc định rõ ràng, cho phép ghi đè có chủ đích từ bên ngoài và tránh những thay đổi ngoài dự kiến trong quá trình build.

