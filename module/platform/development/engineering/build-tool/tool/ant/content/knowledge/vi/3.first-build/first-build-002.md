# Tạo `build.xml` tối thiểu với `project` và target mặc định

Apache Ant đọc các chỉ dẫn build từ một tệp XML. Tệp này thường được đặt tên là `build.xml` và mô tả dự án cùng những công việc mà Ant cần thực hiện. Trong một build file nhỏ nhất, phần tử gốc `<project>` khai báo dự án, thuộc tính `default` chỉ định target mặc định, còn phần tử `<target>` chứa các task cần chạy.

Khi đã có `build.xml` hợp lệ, bạn có thể mở terminal tại thư mục chứa tệp và chạy lệnh `ant`. Ant sẽ đọc build file mặc định và thực thi target được chỉ định bởi thuộc tính `default`.

## 1. Vai trò của build file

Build file là bản mô tả các bước tự động hóa một dự án. Nó không phải tệp mã nguồn Java và cũng không phải một script shell. Ant đọc cấu trúc XML, xác định target cần chạy, rồi thực thi các task nằm trong target đó.

Một build file tối thiểu có ba thành phần:

- `<project>`: phần tử gốc, đại diện cho một dự án Ant và chứa các target.
- `<target>`: một nhóm công việc có tên. Target có thể chứa một hoặc nhiều task.
- Task: hành động cụ thể mà Ant thực hiện, chẳng hạn in thông báo, tạo thư mục hoặc biên dịch mã nguồn.

Ví dụ dưới đây chỉ dùng task `<echo>` để in thông báo. Mục tiêu của ví dụ là hiểu cấu trúc build file và cơ chế chọn target mặc định; nó chưa biên dịch một chương trình Java.

## 2. Cấu trúc tối thiểu của `build.xml`

Tạo một thư mục mới, chẳng hạn `ant-first-build`, rồi tạo tệp `build.xml` bên trong thư mục đó:

```text
ant-first-build/
└── build.xml
```

Đặt nội dung sau vào `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="hello-ant" default="hello" basedir=".">

    <target name="hello">
        <echo message="Hello, Apache Ant!"/>
    </target>

</project>
```

Đây là một build file hoàn chỉnh. Tệp có khai báo XML, một phần tử `<project>` và một target tên `hello`. Khi chạy Ant mà không chỉ định target, Ant sẽ chọn `hello` vì thuộc tính `default` của project đang trỏ đến tên đó.

### 2.1. Phần tử gốc `<project>`

`<project>` bao quanh toàn bộ cấu hình của một build file. Một build file có một phần tử gốc `<project>`; các target được khai báo bên trong phần tử này.

Trong ví dụ:

```xml
<project name="hello-ant" default="hello" basedir=".">
```

Ba thuộc tính đang được sử dụng có ý nghĩa như sau:

| Thuộc tính | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| `name` | `hello-ant` | Tên của project trong build file, giúp nhận diện dự án trong cấu hình và thông tin build |
| `default` | `hello` | Tên target Ant sẽ chạy khi người dùng không chỉ định target trên dòng lệnh |
| `basedir` | `.` | Thư mục cơ sở để phân giải các đường dẫn tương đối trong build file; dấu chấm biểu thị thư mục cơ sở của build file |

Các thuộc tính XML phân biệt chữ hoa và chữ thường. Hãy viết đúng tên thuộc tính và đặt giá trị chuỗi trong dấu nháy. Nếu `default="hello"`, build file phải có target mang tên `hello` để lệnh chạy mặc định có thể thực hiện được.

`basedir` đặc biệt hữu ích khi build file bắt đầu tham chiếu đến thư mục mã nguồn, thư mục đầu ra hoặc các tệp cấu hình khác. Ví dụ, nếu có thư mục `src` cùng cấp với `build.xml`, đường dẫn tương đối `src` được phân giải dựa trên thư mục cơ sở đã khai báo.

### 2.2. Khai báo target bằng `<target>`

Target là một đơn vị công việc có tên trong build file. Cấu trúc cơ bản:

```xml
<target name="ten-target">
    <!-- Các task của target -->
</target>
```

Trong ví dụ ban đầu:

```xml
<target name="hello">
    <echo message="Hello, Apache Ant!"/>
</target>
```

Thuộc tính `name` đặt tên cho target. Tên này được dùng trong thuộc tính `default` hoặc trên dòng lệnh để yêu cầu Ant chạy target cụ thể.

Các task được đặt bên trong target sẽ được thực thi theo thứ tự xuất hiện trong build file. Ví dụ chỉ có một task `<echo>`, vì vậy Ant in một dòng thông báo khi target chạy.

Không đặt target bên ngoài `<project>`. Mỗi target cần có tên phù hợp để có thể được tham chiếu rõ ràng. Nếu `default` trỏ đến một tên target không tồn tại, Ant không thể thực hiện yêu cầu chạy mặc định và build sẽ thất bại.

### 2.3. Task `<echo>`

`<echo>` là task có sẵn của Ant, dùng để ghi thông báo ra đầu ra build. Trong ví dụ:

```xml
<echo message="Hello, Apache Ant!"/>
```

`message` là nội dung cần in. Task này giúp quan sát target có thực sự được thực thi hay không mà không cần chuẩn bị mã nguồn Java, compiler task hay thư viện bên ngoài.

Task có thể được viết thành phần tử XML tự đóng khi không có phần tử con, như `<echo .../>`. XML yêu cầu các phần tử phải được đóng đúng cách; nếu viết dạng mở và đóng thì phải có cặp tương ứng, ví dụ `<target>...</target>`.

## 3. Target mặc định hoạt động như thế nào?

Thuộc tính `default` của `<project>` chứa **tên** target mặc định. Nó không chứa nội dung lệnh, không phải tên task và cũng không phải một từ khóa đặc biệt như `main`.

Với khai báo:

```xml
<project name="hello-ant" default="hello" basedir=".">
```

Ant sẽ tìm target có `name="hello"` khi bạn chạy `ant` mà không ghi tên target. Có thể hình dung luồng xử lý như sau:

```text
Chạy lệnh ant
      |
      v
Ant đọc build.xml trong thư mục hiện tại
      |
      v
Đọc thuộc tính default của project
      |
      v
Tìm target có tên tương ứng
      |
      v
Thực thi các task trong target
      |
      v
Kết thúc build
```

Nếu chạy `ant hello`, bạn đã chỉ định target tường minh trên dòng lệnh. Ant sẽ chạy target `hello` được yêu cầu; thuộc tính `default` chỉ được dùng khi không có target nào được chỉ định.

Target mặc định không bắt buộc phải tên là `default`. Ví dụ, cả hai cách khai báo dưới đây đều hợp lệ nếu target tương ứng tồn tại:

```xml
<project name="demo" default="build">
    <target name="build">
        <echo message="Running build"/>
    </target>
</project>
```

Hoặc:

```xml
<project name="demo" default="start">
    <target name="start">
        <echo message="Starting project"/>
    </target>
</project>
```

Điều quan trọng là giá trị của `default` phải khớp với tên target được khai báo trong project.

## 4. Chạy build file đầu tiên

Trước khi chạy, bảo đảm Apache Ant đã được cài đặt và lệnh `ant` có thể được gọi từ terminal. Mở terminal tại thư mục `ant-first-build`, nơi chứa `build.xml`.

### 4.1. Chạy target mặc định

Thực thi:

```bash
ant
```

Vì lệnh không chỉ định target, Ant sử dụng `default="hello"` trong phần tử `<project>`. Đầu ra sẽ có dạng tương tự:

```text
Buildfile: .../ant-first-build/build.xml

hello:
     [echo] Hello, Apache Ant!

BUILD SUCCESSFUL
Total time: ...
```

Đường dẫn build file và thời gian thực thi phụ thuộc môi trường. Các phần cần quan sát là tên target `hello`, thông báo từ task `<echo>` và trạng thái `BUILD SUCCESSFUL`.

### 4.2. Chỉ định target tường minh

Bạn cũng có thể yêu cầu Ant chạy target bằng tên:

```bash
ant hello
```

Với build file hiện tại, kết quả của lệnh này tương tự lệnh `ant` vì `hello` cũng chính là target mặc định. Khi dự án có nhiều target, cách gọi tường minh giúp chọn đúng công việc muốn thực hiện.

### 4.3. Chỉ định một build file khác

Ant mặc định tìm tệp `build.xml` trong thư mục làm việc hiện tại. Nếu tệp có tên khác hoặc nằm ở vị trí khác, dùng tùy chọn `-f`:

```bash
ant -f path/to/build.xml
```

Có thể kết hợp `-f` với tên target:

```bash
ant -f path/to/build.xml hello
```

Thay `path/to/build.xml` bằng đường dẫn thực tế trên máy. Nếu build file được chỉ định bằng `-f`, Ant đọc đúng tệp đó thay vì tự tìm `build.xml` tại thư mục hiện tại.

## 5. Thử thay đổi target mặc định

Để thấy rõ vai trò của `default`, mở rộng build file thành hai target:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="hello-ant" default="info" basedir=".">

    <target name="hello">
        <echo message="Hello, Apache Ant!"/>
    </target>

    <target name="info">
        <echo message="This is the default target."/>
    </target>

</project>
```

Chạy `ant`, Ant thực thi target `info` vì `default="info"`. Chạy `ant hello`, Ant thực thi target `hello` theo yêu cầu trên dòng lệnh. Hãy thử đổi `default="info"` thành `default="hello"` rồi chạy lại `ant` để quan sát kết quả thay đổi.

Ví dụ này cho thấy tên target mặc định chỉ là một tham chiếu đến target. Bạn có thể chọn target mặc định phù hợp với công việc thường làm khi bắt đầu build dự án.

## 6. Những lỗi cơ bản cần nhận biết

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy build file | Terminal đang ở thư mục không chứa `build.xml`, hoặc build file có tên khác | Chuyển đến đúng thư mục hoặc chỉ định tệp bằng `ant -f path/to/build.xml` |
| Target mặc định không tồn tại | Giá trị `default` không khớp với bất kỳ `name` nào của target | Sửa `default` hoặc khai báo target có tên tương ứng |
| XML parse error | Thiếu thẻ đóng, sai dấu nháy, đặt sai cấu trúc phần tử hoặc ký tự XML không hợp lệ | Kiểm tra lại cấu trúc XML, đặc biệt các cặp `<project>`, `<target>` và phần tử task |
| Ant báo không có target được yêu cầu | Tên target trên dòng lệnh bị viết sai hoặc chưa được khai báo | Đối chiếu tên sau `ant` với thuộc tính `name` của target |
| Lệnh `ant` không chạy được | Ant chưa được cài đặt hoặc thư mục `bin` chưa có trong `PATH` | Kiểm tra cài đặt Ant và biến môi trường trước khi chạy build file |

XML phân biệt chữ hoa và chữ thường. Vì vậy `<project>`, `<Project>` và `<PROJECT>` không phải cùng một tên phần tử. Tương tự, hãy dùng nhất quán tên target trong `default` và `name`.

## 7. Mở rộng từ build file tối thiểu

Khi đã hiểu `<project>` và target mặc định, bạn có thể bổ sung target khác cho các công việc riêng như `clean`, `compile` hoặc `package`. Mỗi target nên có một nhiệm vụ rõ ràng để người đọc dễ hiểu và có thể gọi riêng khi cần.

Một target có thể phụ thuộc vào target khác thông qua thuộc tính `depends`. Ví dụ:

```xml
<project name="demo" default="build" basedir=".">

    <target name="prepare">
        <echo message="Preparing build"/>
    </target>

    <target name="build" depends="prepare">
        <echo message="Building project"/>
    </target>

</project>
```

Khi chạy `ant`, Ant chọn target `build`. Vì `build` phụ thuộc vào `prepare`, Ant thực thi `prepare` trước, sau đó mới chạy task của `build`. Đây là bước mở rộng hữu ích sau khi cấu trúc project và target mặc định đã hoạt động.

Tuy nhiên, nếu mục tiêu chỉ là tạo build file đầu tiên, ví dụ với một target `hello` là đủ. Hãy giữ build file đơn giản cho đến khi dự án thực sự cần thêm bước tự động hóa.

## 8. Checklist tạo build file đầu tiên

- [ ] Tạo tệp `build.xml` trong thư mục dự án.
- [ ] Khai báo một phần tử gốc `<project>`.
- [ ] Đặt `name` để nhận diện project.
- [ ] Đặt `default` trỏ đến tên target sẽ chạy khi không chỉ định target trên dòng lệnh.
- [ ] Khai báo `<target>` có `name` trùng với giá trị `default`.
- [ ] Đặt ít nhất một task hợp lệ bên trong target, chẳng hạn `<echo>`.
- [ ] Chạy `ant` từ thư mục chứa build file và quan sát target mặc định được thực thi.
- [ ] Chạy `ant <target-name>` để xác nhận có thể gọi target tường minh.

Khi lệnh `ant` thực thi được target mặc định và kết thúc với `BUILD SUCCESSFUL`, bạn đã có build file Ant đầu tiên. Cấu trúc `<project>` cùng thuộc tính `default` và phần tử `<target>` là nền tảng để tiếp tục tổ chức những bước build lớn hơn.
