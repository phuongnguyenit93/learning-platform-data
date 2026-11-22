# Tiếp tục các nhánh độc lập bằng `-keep-going`

Một build Ant có thể gồm nhiều nhánh công việc độc lập. Ví dụ, dự án có thể biên dịch hai thành phần riêng, tạo báo cáo cho từng thành phần hoặc đóng gói nhiều ứng dụng trong cùng một lần chạy. Nếu một nhánh gặp lỗi, đôi khi vẫn cần chạy các nhánh còn lại để thu thập thêm kết quả và biết đầy đủ những phần nào đang gặp vấn đề.

Theo mặc định, Ant dừng quá trình build khi gặp lỗi ở một target. Tùy chọn dòng lệnh `-keep-going` cho phép Ant tiếp tục thực hiện những target không phụ thuộc vào target đã thất bại. Tùy chọn viết tắt của nó là `-k`.

## 1. Hành vi mặc định khi một target thất bại

Trong Ant, một target có thể chứa nhiều task và có thể phụ thuộc vào target khác thông qua thuộc tính `depends`. Khi một task thất bại, target chứa task đó thất bại. Theo hành vi mặc định, Ant dừng build thay vì tiếp tục xử lý các target độc lập còn lại.

Ví dụ buildfile sau có hai target độc lập:

```xml
<project name="multi-target-build" default="build-all" basedir=".">

    <target name="compile-api">
        <echo message="Compiling API"/>
        <fail message="Simulated API compilation failure"/>
    </target>

    <target name="compile-ui">
        <echo message="Compiling UI"/>
    </target>

    <target name="build-all" depends="compile-api,compile-ui">
        <echo message="All components have been built"/>
    </target>

</project>
```

Target `compile-api` được cố ý làm thất bại bằng task `<fail>` để minh họa. Target `compile-ui` không phụ thuộc vào `compile-api`, nên về mặt quan hệ target, hai nhánh này độc lập.

Chạy lệnh mặc định:

```sh
ant build-all
```

Khi `compile-api` thất bại, Ant dừng theo hành vi mặc định. Target `compile-ui` có thể chưa được thực hiện dù nó không phụ thuộc vào `compile-api`.

## 2. Dùng `-keep-going` để tiếp tục các target độc lập

Thêm `-keep-going` vào lệnh Ant:

```sh
ant -keep-going build-all
```

Hoặc dùng tùy chọn viết tắt:

```sh
ant -k build-all
```

Khi có lỗi ở `compile-api`, Ant tiếp tục xử lý các target không phụ thuộc vào nhánh thất bại. Trong ví dụ, `compile-ui` vẫn có thể chạy. Target `build-all` không thể hoàn thành vì một prerequisite của nó đã thất bại.

Có thể hình dung quan hệ target như sau:

```text
                 build-all
                 /       \
                /         \
         compile-api    compile-ui
              |              |
            FAIL            PASS
              |
       build-all không thể hoàn thành
```

`-keep-going` cho phép Ant tiếp tục ở nhánh `compile-ui`, nhưng không biến nhánh `compile-api` thành thành công và cũng không làm cho `build-all` được xem là hoàn tất thành công.

## 3. Ví dụ với các nhánh đóng gói độc lập

Trong một dự án thực tế, mỗi nhánh có thể gồm nhiều bước. Ví dụ API cần biên dịch rồi đóng gói, UI cũng cần biên dịch rồi đóng gói:

```xml
<project name="multi-target-build" default="build-all" basedir=".">

    <target name="compile-api">
        <echo message="Compiling API"/>
        <fail message="API compilation failed"/>
    </target>

    <target name="package-api" depends="compile-api">
        <echo message="Packaging API"/>
    </target>

    <target name="compile-ui">
        <echo message="Compiling UI"/>
    </target>

    <target name="package-ui" depends="compile-ui">
        <echo message="Packaging UI"/>
    </target>

    <target name="build-all" depends="package-api,package-ui">
        <echo message="Build completed"/>
    </target>

</project>
```

Chạy:

```sh
ant -keep-going build-all
```

Ant xử lý hai nhánh theo quan hệ phụ thuộc:

- Nhánh API: `compile-api` thất bại, vì vậy `package-api` không được chạy.
- Nhánh UI: `compile-ui` thành công, vì vậy `package-ui` có thể tiếp tục chạy.
- Target `build-all` không thể hoàn tất vì prerequisite `package-api` không hoàn thành.

Tùy chọn này hữu ích khi cần thu thập kết quả của các nhánh độc lập trong một lần build. Ví dụ, dù API lỗi, nhóm phát triển vẫn có thể nhận được log cho biết UI có biên dịch và đóng gói được hay không.

## 4. Quan hệ phụ thuộc quyết định target nào được tiếp tục

`-keep-going` không bỏ qua toàn bộ dependency. Ant vẫn tôn trọng đồ thị phụ thuộc được khai báo bằng `depends`.

| Trạng thái prerequisite | Target phụ thuộc sẽ thế nào? |
|---|---|
| Tất cả prerequisite cần thiết thành công | Target có thể được thực hiện |
| Có prerequisite thất bại | Target phụ thuộc bị bỏ qua vì điều kiện tiên quyết không đạt |
| Một nhánh thất bại, nhánh khác không phụ thuộc vào nó | Ant có thể tiếp tục nhánh độc lập khi bật `-keep-going` |

Ví dụ, nếu `package-api` phụ thuộc `compile-api`, mà `compile-api` thất bại, Ant không chạy `package-api`. Việc bật `-keep-going` không có nghĩa là ép `package-api` chạy bất chấp lỗi biên dịch.

Khi thiết kế buildfile, hãy mô tả đúng quan hệ thực sự giữa các bước. Không khai báo dependency chỉ để ép các target chạy theo thứ tự nếu chúng không cần kết quả của nhau; ngược lại, không bỏ dependency thật chỉ để có vẻ như các nhánh độc lập.

## 5. Chạy nhiều target độc lập trực tiếp từ dòng lệnh

Ant cho phép chỉ định nhiều target trong cùng một lệnh. `-keep-going` cũng có thể hữu ích trong trường hợp này:

```sh
ant -keep-going compile-api compile-ui
```

Ant lần lượt xử lý các target được yêu cầu. Nếu target đầu tiên thất bại, tùy chọn này cho phép tiếp tục target tiếp theo nếu target đó không phụ thuộc vào target đã thất bại.

Không bật `-keep-going`:

```sh
ant compile-api compile-ui
```

Ant áp dụng hành vi mặc định và dừng khi gặp lỗi.

Nếu các target có phụ thuộc lẫn nhau, Ant vẫn xử lý theo dependency của chúng. Việc truyền nhiều tên target không loại bỏ hay thay đổi quan hệ `depends` trong buildfile.

## 6. `-keep-going` không có nghĩa là bỏ qua lỗi

Đây là điểm quan trọng khi sử dụng tùy chọn này trong quy trình build:

- Ant vẫn ghi nhận lỗi của task và target đã thất bại.
- Những task còn lại trong chính target đã thất bại không tự động được chạy tiếp sau task gây lỗi.
- Target phụ thuộc vào target thất bại sẽ không được thực hiện nếu prerequisite đó không hoàn thành.
- Chỉ các target độc lập với lỗi mới có thể tiếp tục.
- Build vẫn được xem là thất bại nếu có target thất bại; tùy chọn này không đổi mã thoát lỗi thành thành công.

Vì vậy, `-keep-going` không tương đương với việc bỏ qua lỗi hoặc ép build luôn thành công. Nó chỉ giúp thực hiện thêm những công việc còn có thể chạy hợp lệ sau khi một nhánh gặp lỗi.

## 7. Khi nào nên dùng `-keep-going`?

Tùy chọn này hữu ích trong các tình huống như:

- Build nhiều module hoặc nhiều ứng dụng độc lập trong một repository.
- Chạy nhiều nhóm kiểm thử độc lập và muốn thu thập thêm kết quả dù một nhóm đã lỗi.
- Tạo báo cáo cho nhiều thành phần trong cùng một lần chạy.
- Kiểm tra nhiều target đầu ra độc lập trước khi tổng hợp kết quả build.

Không nên dùng nó để che giấu lỗi hoặc thay thế việc sửa nguyên nhân thất bại. Nếu target sau thực sự cần artifact do target trước tạo ra, hãy giữ quan hệ dependency và để Ant bỏ qua bước sau khi prerequisite thất bại.

## 8. Kết hợp với log để tìm nguyên nhân

Khi bật `-keep-going`, log có thể chứa lỗi từ nhiều nhánh. Hãy đọc log theo tên target và tìm thông báo lỗi đầu tiên của từng nhánh, sau đó kiểm tra những target bị bỏ qua do phụ thuộc.

Một số lệnh hữu ích:

```sh
ant -keep-going -verbose build-all
ant -keep-going -logfile build.log build-all
```

- `-verbose` hiển thị thêm thông tin về quá trình thực thi để giúp xác định target và task đang chạy.
- `-logfile build.log` ghi log vào tệp để có thể xem lại sau khi lệnh kết thúc.

Khi build kết thúc, hãy phân biệt ba nhóm thông tin:

1. Target đã chạy thành công.
2. Target thất bại và task gây lỗi.
3. Target bị bỏ qua vì phụ thuộc vào target thất bại.

Việc phân loại này giúp xác định lỗi gốc và tránh nhầm target bị bỏ qua với target đã chạy nhưng thất bại.

## 9. Lỗi thường gặp khi sử dụng `-keep-going`

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ant vẫn dừng ở lỗi đầu tiên | Chưa truyền `-keep-going` hoặc `-k` vào lệnh | Chạy lại với `ant -keep-going <target>` |
| Target sau không chạy dù đã bật tùy chọn | Target đó phụ thuộc vào target đã thất bại | Kiểm tra `depends`; target phụ thuộc cần prerequisite thành công |
| Build chạy thêm target nhưng kết quả cuối vẫn báo lỗi | Có ít nhất một target thất bại | Đọc lỗi gốc và sửa nguyên nhân; `-keep-going` không biến build lỗi thành thành công |
| Log có nhiều thông báo lỗi và target bị bỏ qua | Ant tiếp tục xử lý các nhánh khác và báo các hậu quả phụ thuộc | Phân biệt lỗi gốc với target bị bỏ qua do dependency |
| Target độc lập không được chạy như dự kiến | Dependency được khai báo quá rộng hoặc nhầm quan hệ giữa các target | Xem lại đồ thị phụ thuộc và chỉ liên kết những bước thực sự cần kết quả của nhau |

## 10. Checklist sử dụng

- [ ] Đã xác định các target có thể chạy độc lập.
- [ ] Quan hệ `depends` phản ánh đúng prerequisite thực tế.
- [ ] Đã thêm `-keep-going` hoặc `-k` vào lệnh Ant khi muốn tiếp tục nhánh độc lập.
- [ ] Đã kiểm tra target nào thất bại và target nào bị bỏ qua do dependency.
- [ ] Đã xem log của các nhánh tiếp tục chạy để thu thập kết quả.
- [ ] Vẫn xử lý mã thoát lỗi của build như một lần build thất bại nếu có target thất bại.

Khi sử dụng đúng, `-keep-going` giúp một lần chạy Ant thu thập được nhiều kết quả hơn từ các nhánh độc lập. Buildfile vẫn giữ nguyên logic phụ thuộc, các lỗi vẫn được báo cáo và những bước cần đầu vào chưa tạo được sẽ không chạy sai thứ tự.
