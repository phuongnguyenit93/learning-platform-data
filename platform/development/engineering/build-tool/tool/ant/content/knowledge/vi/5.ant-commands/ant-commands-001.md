# Chọn buildfile bằng -f, -file và -buildfile

Khi chạy Apache Ant trong một dự án đơn giản, ta thường đặt file cấu hình tên `build.xml` ở thư mục gốc rồi gõ `ant`. Tuy nhiên, một repository có thể chứa nhiều file build: một file cho ứng dụng chính, một file cho từng module, một file dành cho CI hoặc một file cấu hình riêng cho môi trường phát triển. Khi đó, cần chỉ rõ Ant phải đọc file nào.

Ant cung cấp ba tùy chọn dòng lệnh `-f`, `-file` và `-buildfile` để chọn buildfile. **Cả ba là các cách viết tương đương của cùng một tùy chọn**: chúng yêu cầu Ant sử dụng file build được chỉ định thay vì file mặc định. Khác biệt chỉ nằm ở độ ngắn của cú pháp; cách Ant đọc file và thực hiện target không thay đổi.

## 1. Buildfile mặc định và khi nào cần chọn file khác

Buildfile là file XML mô tả project, target, task, property và quan hệ phụ thuộc mà Ant sẽ thực thi. Theo cách dùng thông thường, tên file là `build.xml`.

Nếu đứng trong thư mục chứa `build.xml` và chạy:

```bash
ant
```

Ant tìm buildfile mặc định trong thư mục làm việc hiện tại. Nếu file có khai báo target mặc định bằng thuộc tính `default` của phần tử `project`, Ant thực hiện target đó cùng các target phụ thuộc. Nếu muốn gọi một target cụ thể, ta ghi tên target sau lệnh:

```bash
ant clean
ant compile
ant clean jar
```

Trong thực tế, file build có thể mang tên khác hoặc nằm trong thư mục con:

```text
hello-ant/
├── build.xml
├── ci/
│   └── build-ci.xml
├── local/
│   └── build-dev.xml
└── modules/
    ├── api/
    │   └── build.xml
    └── worker/
        └── build.xml
```

Ở cấu trúc này, mỗi file có thể mô tả một quy trình hoặc một phạm vi build riêng. Nếu chỉ gõ `ant` tại thư mục `hello-ant`, Ant sẽ dùng `hello-ant/build.xml`; nó không tự chọn file trong `ci/`, `local/` hoặc một module con.

Ta cần chọn buildfile tường minh khi:

- File build không có tên `build.xml`.
- File build nằm ngoài thư mục làm việc hiện tại.
- Có nhiều file `build.xml` và cần chọn đúng module.
- Muốn chạy quy trình dành riêng cho CI, kiểm thử, đóng gói hoặc môi trường phát triển.
- Script cần gọi một file build ổn định, không phụ thuộc vào việc người dùng đang đứng ở thư mục nào trong repository.

## 2. Ba tùy chọn -f, -file và -buildfile

Cú pháp chung của lệnh Ant có thể hình dung như sau:

```text
ant [options] [target [target2 ...]]
```

Để chọn buildfile, đặt một trong ba tùy chọn cùng đường dẫn file trước các target cần chạy:

```bash
ant -f <buildfile> [target ...]
ant -file <buildfile> [target ...]
ant -buildfile <buildfile> [target ...]
```

Ý nghĩa của chúng giống nhau:

| Tùy chọn | Ý nghĩa | Đặc điểm |
|---|---|---|
| `-f` | Dùng buildfile được chỉ định | Ngắn gọn, thuận tiện khi gõ trực tiếp hoặc viết script |
| `-file` | Dùng buildfile được chỉ định | Tên dễ đọc, diễn đạt rõ mục đích |
| `-buildfile` | Dùng buildfile được chỉ định | Tên đầy đủ, thường dễ hiểu khi đọc lệnh dài |

Ví dụ, ba lệnh dưới đây chọn cùng một file và gọi cùng target:

```bash
ant -f ci/build-ci.xml clean jar
ant -file ci/build-ci.xml clean jar
ant -buildfile ci/build-ci.xml clean jar
```

Nếu file build và môi trường giống nhau, kết quả thực thi của ba lệnh là tương đương. Không có một tùy chọn nào trong ba tùy chọn trên tự động bật chế độ CI, thay đổi cách biên dịch hay thay đổi thứ tự target.

## 3. Ví dụ chọn buildfile trong repository

Giả sử terminal đang đứng ở thư mục gốc `hello-ant/` và repository có cấu trúc như trên.

### 3.1. Chọn buildfile dành cho CI

Muốn chạy target `verify` trong file `ci/build-ci.xml`:

```bash
ant -f ci/build-ci.xml verify
```

Hoặc dùng tên tùy chọn đầy đủ:

```bash
ant -buildfile ci/build-ci.xml verify
```

Ant sẽ đọc `ci/build-ci.xml`, sau đó tìm target `verify` trong project được khai báo ở file đó. Target mặc định của `build.xml` tại thư mục gốc không được chọn trong lệnh này.

### 3.2. Chọn buildfile của một module

Muốn đóng gói riêng module `api`:

```bash
ant -f modules/api/build.xml clean jar
```

Lệnh yêu cầu Ant đọc file build của module `api`, rồi thực hiện các target `clean` và `jar` theo quy tắc của file đó. Nếu module `api` có target `jar` phụ thuộc vào `compile`, Ant vẫn xử lý quan hệ phụ thuộc được khai báo trong chính project này.

### 3.3. Chọn buildfile nhưng không chỉ rõ target

Có thể gọi:

```bash
ant -f local/build-dev.xml
```

Khi không có tên target ở cuối lệnh, Ant sử dụng target mặc định được khai báo trong phần tử `project` của `local/build-dev.xml`. Ví dụ:

```xml
<project name="hello-ant-dev" default="run-local">
    <target name="compile">
        <!-- Biên dịch cho môi trường phát triển. -->
    </target>

    <target name="run-local" depends="compile">
        <!-- Chạy ứng dụng trong môi trường phát triển. -->
    </target>
</project>
```

Trong ví dụ này, `ant -f local/build-dev.xml` sẽ chọn target mặc định `run-local`. Nếu muốn chạy một target khác, hãy ghi tên target rõ ràng, chẳng hạn `ant -f local/build-dev.xml compile`.

## 4. Chọn file bằng đường dẫn tương đối và tuyệt đối

Đối số đứng sau `-f`, `-file` hoặc `-buildfile` là đường dẫn đến file XML mà Ant cần đọc.

### 4.1. Đường dẫn tương đối

Đường dẫn tương đối được hiểu dựa trên thư mục làm việc hiện tại của tiến trình Ant, tức thư mục terminal đang đứng khi gọi lệnh.

Ví dụ, terminal đang đứng tại:

```text
/workspace/hello-ant
```

và file build nằm tại:

```text
/workspace/hello-ant/ci/build-ci.xml
```

Ta có thể chạy:

```bash
ant -f ci/build-ci.xml verify
```

Đường dẫn `ci/build-ci.xml` được tính từ `/workspace/hello-ant`. Nếu chuyển terminal sang một thư mục khác mà vẫn giữ nguyên đối số tương đối, Ant có thể không tìm thấy file.

Ví dụ, nếu terminal đang đứng ở `/workspace`, lệnh tương ứng phải là:

```bash
ant -f hello-ant/ci/build-ci.xml verify
```

### 4.2. Đường dẫn tuyệt đối

Đường dẫn tuyệt đối chỉ rõ vị trí file từ gốc của hệ thống file. Cách này hữu ích khi script được gọi từ nhiều thư mục khác nhau:

```bash
ant -f /workspace/hello-ant/ci/build-ci.xml verify
```

Trên Windows, ví dụ:

```powershell
ant -f 'C:\work\hello-ant\ci\build-ci.xml' verify
```

Đường dẫn tuyệt đối giảm phụ thuộc vào thư mục hiện tại, nhưng script sẽ phụ thuộc vào vị trí checkout hoặc cách tổ chức ổ đĩa trên máy chạy. Trong CI, thường nên dựng đường dẫn từ thư mục workspace mà hệ thống CI cung cấp.

### 4.3. Đường dẫn có khoảng trắng

Nếu đường dẫn chứa khoảng trắng, hãy đặt toàn bộ đường dẫn trong dấu nháy kép hoặc nháy đơn phù hợp với shell:

```powershell
ant -f "C:\work\My Java Project\build-ci.xml" verify
```

```bash
ant -f "/home/dev/My Java Project/build-ci.xml" verify
```

Không đặt dấu nháy chỉ quanh một phần của đường dẫn. Nếu bỏ dấu nháy, shell có thể tách đường dẫn thành nhiều đối số, khiến Ant hiểu sai tên file hoặc target.

## 5. Phân biệt buildfile được chọn và thư mục làm việc

Đây là điểm dễ gây nhầm khi dùng `-f`: **chọn một file build không đồng nghĩa với việc đổi thư mục làm việc của shell**.

Có hai khái niệm riêng:

- **Thư mục làm việc hiện tại:** nơi terminal hoặc tiến trình gọi Ant đang đứng. Nó ảnh hưởng đến cách phân giải đường dẫn tương đối được truyền trên dòng lệnh, chẳng hạn `ci/build.xml`.
- **Project basedir:** thư mục gốc mà các đường dẫn tương đối trong buildfile được tính theo. Nó được xác định bởi thuộc tính `basedir` của phần tử `project`; nếu không khai báo, Ant mặc định dùng thư mục cha của buildfile. Cấu hình property `basedir` cũng có thể tham gia điều khiển giá trị này.

Ví dụ, repository có:

```text
hello-ant/
├── ci/
│   └── build-ci.xml
└── src/
    └── main/java/
```

Ta đứng ở thư mục `hello-ant` và chạy:

```bash
ant -f ci/build-ci.xml verify
```

Đường dẫn `ci/build-ci.xml` được tìm từ thư mục làm việc `hello-ant`. Sau khi file được nạp, các đường dẫn tương đối trong build được xử lý theo project basedir. Nếu buildfile không đặt `basedir` và không có cấu hình ghi đè, basedir mặc định là thư mục chứa buildfile, tức `hello-ant/ci`.

Nếu buildfile muốn lấy thư mục gốc repository làm basedir, có thể khai báo tường minh theo cấu trúc dự án. Ví dụ, với buildfile nằm trong thư mục `ci`:

```xml
<project name="hello-ant-ci" default="verify" basedir="..">
    <property name="src.dir" location="src/main/java"/>

    <target name="verify">
        <echo message="Source directory: ${src.dir}"/>
    </target>
</project>
```

Trong ví dụ này, `basedir=".."` đưa project basedir lên thư mục cha của `ci`, tức thư mục gốc `hello-ant`. Vì vậy, `src.dir` trỏ đến `hello-ant/src/main/java`.

Khi debug lỗi không tìm thấy file, hãy kiểm tra cả đường dẫn buildfile trên dòng lệnh và `basedir` của project. Hai giá trị này giải quyết hai việc khác nhau.

## 6. Kết hợp tùy chọn chọn buildfile với target

Chọn buildfile chỉ quyết định Ant đọc cấu hình nào. Target ở cuối lệnh quyết định công việc nào trong cấu hình đó cần chạy.

Ví dụ:

```bash
# Dùng target mặc định của build-ci.xml
ant -f ci/build-ci.xml

# Chỉ chạy compile
ant -f ci/build-ci.xml compile

# Chạy clean rồi jar
ant -f ci/build-ci.xml clean jar

# Chạy nhiều target theo thứ tự yêu cầu
ant -f ci/build-ci.xml clean test jar
```

Khi gọi nhiều target trên cùng dòng lệnh, Ant xử lý các target theo thứ tự được yêu cầu, đồng thời thực hiện các target phụ thuộc cần thiết. Nếu nhiều target cùng phụ thuộc vào một target, Ant không nhất thiết thực hiện lại target đó nhiều lần trong cùng một lượt build.

Hãy đảm bảo target tồn tại trong file build được chọn. Một target có trong `build.xml` ở thư mục gốc không tự động tồn tại trong `ci/build-ci.xml` hoặc `modules/api/build.xml`.

Ví dụ, lệnh sau có thể thất bại nếu file CI không khai báo target `deploy`:

```bash
ant -f ci/build-ci.xml deploy
```

Thông báo lỗi về target không tồn tại cần được xử lý bằng cách kiểm tra đúng file build và tên target, không phải bằng cách đổi ngẫu nhiên các tùy chọn `-f`, `-file` hoặc `-buildfile`.

## 7. Một buildfile trong mỗi lần gọi Ant

Mỗi tùy chọn `-f`, `-file` hoặc `-buildfile` chọn một buildfile cho một tiến trình Ant. Ta có thể gọi nhiều target trong cùng file, nhưng không dùng một tùy chọn này để yêu cầu Ant tự động hợp nhất nhiều file build độc lập.

Nếu cần thực hiện nhiều dự án độc lập, có thể gọi Ant nhiều lần:

```bash
ant -f modules/api/build.xml clean jar
ant -f modules/worker/build.xml clean jar
```

Hoặc thiết kế một buildfile điều phối và sử dụng task phù hợp như `<ant>` hoặc `<subant>` để gọi các build con. Đó là cơ chế điều phối project từ bên trong build, khác với việc chọn buildfile đầu vào bằng tùy chọn dòng lệnh.

Trong trường hợp chỉ muốn chia sẻ các đoạn cấu hình, Ant còn có các cơ chế như `<import>` để nạp nội dung build từ file khác. Cơ chế này cũng khác với `-f`: `-f` chọn file gốc mà tiến trình bắt đầu đọc, còn `import` là chỉ thị nằm trong file build để đưa nội dung từ file khác vào project.

## 8. Kết hợp với các tùy chọn Ant khác

Tùy chọn chọn buildfile có thể dùng cùng các tùy chọn dòng lệnh khác, chẳng hạn property `-D`, mức log hoặc chế độ tiếp tục khi có lỗi.

```bash
# Truyền property cho file build được chọn
ant -f ci/build-ci.xml -Denv=staging verify

# Tăng mức thông tin khi chạy target
ant -f ci/build-ci.xml -verbose verify

# Tiếp tục các target độc lập khi một target thất bại
ant -f ci/build-ci.xml -keep-going build-all
```

Trong ví dụ đầu, `${env}` trong buildfile có thể nhận giá trị `staging` nếu property chưa được thiết lập trước đó. Trong ví dụ thứ hai, `-verbose` điều chỉnh mức log. Trong ví dụ thứ ba, `-keep-going` cho phép Ant tiếp tục một số target độc lập sau lỗi để thu thập thêm kết quả; toàn bộ build vẫn có thể kết thúc thất bại.

Nên đặt tùy chọn và đối số rõ ràng để người đọc nhận biết đâu là đường dẫn buildfile, đâu là property và đâu là target. Một lệnh dễ đọc cũng giúp giảm lỗi khi chuyển từ terminal sang script CI.

## 9. Các lỗi thường gặp khi chọn buildfile

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| Không tìm thấy buildfile | Đường dẫn tương đối tính từ thư mục làm việc khác với dự kiến hoặc file không tồn tại | Kiểm tra thư mục hiện tại, đường dẫn và tên file; thử đường dẫn tuyệt đối |
| Đã chọn đúng file nhưng không tìm thấy target | Target không được khai báo trong file đó hoặc tên target bị gõ sai | Mở đúng buildfile và kiểm tra tên target; dùng `ant -p` với cùng tùy chọn file để xem project help |
| Lệnh chọn nhầm buildfile mặc định | Bỏ quên `-f` hoặc đặt đường dẫn sai vị trí đối số | Ghi rõ `ant -f path/to/build.xml target` |
| Đường dẫn có khoảng trắng bị tách | Không đặt toàn bộ đối số đường dẫn trong dấu nháy | Trích dẫn đường dẫn theo cú pháp của shell |
| File được đọc nhưng không tìm thấy source hoặc resource | Project basedir khác với giả định | Kiểm tra thuộc tính `basedir`, property `basedir` và các đường dẫn tương đối trong buildfile |
| Chạy được ở máy cá nhân nhưng CI không tìm thấy file | Workspace CI hoặc thư mục làm việc khác | Dùng đường dẫn được tạo từ workspace của CI hoặc chuyển đến thư mục gốc trước khi gọi Ant |
| Thay `-f` bằng `-file` nhưng lỗi vẫn còn | Ba tùy chọn là alias tương đương nên không thay đổi nguyên nhân | Kiểm tra đường dẫn, nội dung file và target được yêu cầu |

### 9.1. Không tìm thấy file build

Giả sử nhận được lỗi cho biết Ant không thể đọc `ci/build-ci.xml`. Trước khi sửa file, hãy xác nhận:

1. Terminal đang đứng ở thư mục nào?
2. Đường dẫn tương đối có được tính từ đúng thư mục đó không?
3. Tên file và phần mở rộng có chính xác không?
4. File có thực sự tồn tại tại vị trí đó không?
5. Người chạy Ant có quyền đọc file không?

Nếu chưa chắc đường dẫn tương đối, hãy thử đường dẫn tuyệt đối để tách riêng vấn đề tìm file khỏi các vấn đề khác.

### 9.2. Không tìm thấy target

Khi buildfile đã được nạp nhưng Ant báo không có target yêu cầu, kiểm tra danh sách target của chính file đó:

```bash
ant -f ci/build-ci.xml -projecthelp
```

Hoặc dạng viết tắt:

```bash
ant -f ci/build-ci.xml -p
```

Project help giúp xem các target có mô tả. Một số target không có mô tả có thể không xuất hiện trong phần liệt kê dễ đọc, vì vậy vẫn cần mở file build nếu cần xác nhận đầy đủ. Hãy chắc chắn target được gọi đúng chính tả và đúng project.

### 9.3. File build đúng nhưng đường dẫn source sai

Đây thường là lỗi nhầm giữa đường dẫn dùng để chọn buildfile và `basedir` của project. Ví dụ, Ant đã đọc được `ci/build-ci.xml`, nhưng task `javac` lại tìm source ở `ci/src` trong khi source thật ở `src` của repository.

Hãy kiểm tra `basedir` trong phần tử `<project>` và các property `src.dir`, `resources.dir`, `build.dir`. Đường dẫn tương đối trong các thuộc tính này phải được tính theo đúng project basedir mong muốn.

## 10. Dùng -f trong script và CI/CD

Trong script tự động hóa, chọn buildfile tường minh giúp lệnh dễ hiểu và ít phụ thuộc vào vị trí gọi. Tuy nhiên, script vẫn cần xác định workspace chính xác và truyền mã thoát của Ant về cho hệ thống gọi.

### 10.1. Bash

Ví dụ script chạy file build dành cho CI:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${WORKSPACE:-$(pwd)}"
BUILD_FILE="$PROJECT_DIR/ci/build-ci.xml"

if [[ ! -f "$BUILD_FILE" ]]; then
    echo "Buildfile not found: $BUILD_FILE" >&2
    exit 2
fi

ant -f "$BUILD_FILE" clean verify jar
```

Script xác định đường dẫn buildfile từ workspace, kiểm tra file tồn tại rồi gọi Ant với target cần thiết. `set -e` khiến script dừng khi lệnh thất bại trong các trường hợp thông thường; `set -u` báo lỗi khi dùng biến chưa được đặt; `pipefail` giúp bảo toàn lỗi trong pipeline. Nếu cần xử lý lỗi tùy chỉnh, có thể dùng cấu trúc `if ant ...; then ... else ... fi` để ghi nhận mã thoát.

### 10.2. PowerShell

Ví dụ tương tự trong PowerShell:

```powershell
$projectDir = if ($env:WORKSPACE) { $env:WORKSPACE } else { (Get-Location).Path }
$buildFile = Join-Path $projectDir 'ci/build-ci.xml'

if (-not (Test-Path -LiteralPath $buildFile -PathType Leaf)) {
    Write-Error "Buildfile not found: $buildFile"
    exit 2
}

ant -f $buildFile clean verify jar
$antExitCode = $LASTEXITCODE

if ($antExitCode -ne 0) {
    Write-Error "Ant build failed with exit code $antExitCode"
    exit $antExitCode
}
```

Script sử dụng `Join-Path` để ghép đường dẫn, kiểm tra file trước khi gọi Ant và trả lại mã thoát của Ant nếu build thất bại. Trong PowerShell, cần đọc `$LASTEXITCODE` ngay sau chương trình native; không dùng `$?` thay cho mã số thoát.

### 10.3. Nguyên tắc khi đưa vào pipeline

- Chọn rõ file build mà pipeline cần chạy; tránh dựa vào buildfile mặc định nếu repository có nhiều file.
- Dùng đường dẫn theo workspace mà runner cung cấp, không hard-code đường dẫn chỉ tồn tại trên máy cá nhân.
- Ghi rõ target cần chạy để log pipeline cho biết mục tiêu thực tế.
- Bảo toàn exit code của Ant. Không để một lệnh ghi log thành công che mất lỗi build.
- Nếu có nhiều buildfile/module, xác định rõ thứ tự và điều kiện chạy của từng lệnh.

## 11. Kết luận

`-f`, `-file` và `-buildfile` là ba cách viết tương đương để chỉ định file XML mà Ant sẽ đọc. `-f` ngắn gọn, `-file` và `-buildfile` dễ diễn đạt hơn khi đọc lệnh; cả ba đều chọn cùng một buildfile và không thay đổi cách target hoạt động.

Khi sử dụng, hãy xác định đường dẫn từ thư mục làm việc hiện tại, đặt dấu nháy nếu đường dẫn có khoảng trắng, rồi chọn target tồn tại trong chính file build đó. Đồng thời phân biệt đường dẫn chọn buildfile với project `basedir`, vì đây là hai khái niệm ảnh hưởng đến hai nhóm đường dẫn khác nhau. Nắm rõ các điểm này giúp gọi đúng quy trình Ant khi dự án có nhiều buildfile, nhiều module hoặc nhiều môi trường thực thi.
