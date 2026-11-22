# Xác minh hai build bằng checksum và so sánh nội dung sản phẩm với Apache Ant

## 1. Vì sao phải so sánh sản phẩm của hai lần build?

Một dự án có thể chạy `ant dist` thành công hai lần nhưng tạo ra hai tệp JAR khác nhau. Thông báo `BUILD SUCCESSFUL` chỉ xác nhận các tác vụ Ant hoàn tất; nó **không chứng minh** rằng các byte đầu ra giống nhau.

Trong chủ đề **Build tái lập (reproducible build)**, câu hỏi quan trọng là:

> Với cùng mã nguồn, cùng đầu vào và cùng bộ công cụ đã kiểm soát, hai lần build độc lập có tạo ra cùng một tập sản phẩm và cùng nội dung byte hay không?

Ta cần kiểm tra ở hai cấp:

1. **Cấp sản phẩm:** Danh sách đường dẫn tương đối, số lượng tệp và giá trị băm SHA-256 của từng tệp đầu ra có trùng nhau không?
2. **Cấp nội dung bên trong:** Nếu một JAR/ZIP có checksum khác nhau, những entry nào bên trong thật sự thay đổi? Hay chỉ metadata của gói nén (thời gian, thứ tự entry, cách nén, quyền tệp) khác nhau?

Ví dụ, hai bản `dist/demo.jar` có thể chạy giống nhau nhưng khác byte vì mốc thời gian lưu trong ZIP. Ngược lại, hai bản JAR có cùng tên tệp không có nghĩa là lớp `.class`, tài nguyên hoặc manifest bên trong giống nhau.

### Tiêu chí và giới hạn của phép xác minh

| Phép kiểm tra | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| Hai tác vụ `ant dist` đều thành công | Cả hai lượt build hoàn tất | Sản phẩm giống nhau |
| Hai tệp có cùng kích thước | Số byte bằng nhau | Nội dung byte bằng nhau |
| SHA-256 của cùng một tệp bằng nhau | Có cơ sở rất mạnh để coi nội dung byte giống hệt nhau | Toàn bộ tập sản phẩm hoặc hành vi ứng dụng đều giống nhau |
| Danh sách đường dẫn và SHA-256 của **mọi** sản phẩm bằng nhau | Tập tệp được so sánh có nội dung byte giống nhau | Quyền thực thi, liên kết tượng trưng, thư mục rỗng hoặc môi trường chạy giống nhau |
| Giải nén hai JAR, các entry có nội dung giống nhau | Payload đã giải nén giống nhau | Byte của hai tệp JAR gốc giống nhau |

SHA-256 là hàm băm mật mã tạo chuỗi 256 bit. Xác suất va chạm ngẫu nhiên rất nhỏ, nên phù hợp để xác minh sản phẩm build. Tuy vậy, nếu cần xác nhận **trực tiếp** từng byte, có thể kết hợp `cmp`/so sánh nhị phân; checksum không thay thế việc kiểm soát nguồn gốc đầu vào, kiểm thử hay xác minh chữ ký phát hành.

## 2. Xác định ranh giới đầu vào và đầu ra

Để phép so sánh có ý nghĩa, trước tiên cần biết chính xác Ant sẽ tạo gì và điều gì có thể tác động đến kết quả.

~~~text
                         ĐẦU VÀO ĐÃ KIỂM SOÁT
  mã nguồn + resources + build.xml + dependency + JDK + Ant
                               |
                               v
                       ant clean dist
                               |
                               v
                    dist/ (sản phẩm cần đo)
                               |
                      lưu snapshot độc lập
                               |
               +---------------+---------------+
               |                               |
          run-1/dist                        run-2/dist
               |                               |
               +------- tập tệp + SHA-256 ------+
                               |
                       so sánh, phân tích
~~~

Những thông tin nên cố định và ghi lại trước hai lượt:

- **Mã nguồn và tài nguyên:** cùng commit hoặc cùng cây nguồn; không sửa file giữa các lượt.
- **Cấu hình Ant:** cùng `build.xml`, file `.properties` và các tham số `-D...`; xác định rõ target xuất bản, chẳng hạn `dist` hoặc `package`.
- **Toolchain:** cùng phiên bản Ant, Java/JDK, trình biên dịch và các công cụ được gọi bởi `<exec>`.
- **Dependency:** cùng phiên bản, đúng nội dung JAR phụ thuộc; tốt nhất khóa phiên bản và kiểm tra checksum của dependency đầu vào. Thay đổi artifact bên ngoài có thể làm thay đổi kết quả dù mã nguồn không đổi.
- **Môi trường:** thống nhất locale, timezone, charset, biến môi trường có ảnh hưởng, đường dẫn, hệ điều hành và quyền tệp ở lượt kiểm cơ sở.
- **Phạm vi đầu ra:** chỉ so sánh sản phẩm dự định giao hoặc triển khai, ví dụ toàn bộ `dist/`. Không vô tình đưa log chạy, thư mục snapshot hoặc file checksum sinh thêm vào cùng phạm vi so sánh.

Nên bắt đầu bằng **hai lượt clean build liên tiếp trên cùng máy**, sau đó mới tăng độ khó bằng hai thư mục checkout, hai runner CI hoặc hai máy độc lập. Việc cùng checksum trên một máy là bằng chứng cho tình huống đã thử, chưa tự động chứng minh tái lập trên mọi môi trường.

## 3. Dự án Ant mẫu để thực hành

Giả sử một dự án Java nhỏ có cấu trúc:

~~~text
ant-demo/
├── build.xml
└── src/
    └── example/
        └── Hello.java
~~~

`src/example/Hello.java`:

~~~java
package example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Ant");
    }
}
~~~

`build.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-demo" default="dist" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="build.dir" location="build"/>
    <property name="dist.dir" location="dist"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${build.dir}/classes"/>
        <javac srcdir="${src.dir}"
               destdir="${build.dir}/classes"
               includeantruntime="false"
               encoding="UTF-8"
               release="17"/>
    </target>

    <target name="dist" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/demo.jar"
             basedir="${build.dir}/classes">
            <manifest>
                <attribute name="Main-Class" value="example.Hello"/>
            </manifest>
        </jar>
    </target>

    <target name="checksum" depends="dist">
        <checksum file="${dist.dir}/demo.jar"
                  algorithm="SHA-256"
                  property="demo.sha256"/>
        <echo message="demo.jar SHA-256: ${demo.sha256}"/>
    </target>
</project>
~~~

Ví dụ dùng **JDK 17 trở lên** và Ant hỗ trợ thuộc tính `release` của tác vụ `javac` (Ant 1.9.8 trở lên; nên dùng Ant 1.10.x). `includeantruntime="false"` tránh tự động trộn thư viện runtime của Ant vào classpath biên dịch. `encoding="UTF-8"` quy định mã hóa nguồn. Tác vụ `jar` đóng gói tệp `.class`, nhưng cấu hình mẫu **chưa bảo đảm JAR tái lập tuyệt đối**: metadata thời gian của các entry vẫn cần được kiểm tra.

Đứng trong thư mục `ant-demo` và ghi nhận:

~~~bash
ant -version
java -version
ant -p
~~~

Nếu dùng Git, có thể lưu thêm `git rev-parse HEAD` và tình trạng thay đổi của cây làm việc. Lệnh `ant -p` giúp xem target được công khai; trong dự án thực tế hãy thay `dist` bằng target tạo sản phẩm tương ứng.

## 4. Chạy hai clean build và lưu hai snapshot

Điểm cốt lõi là **mỗi lần đều dọn đầu ra cũ**, rồi sao chép sản phẩm đi trước khi lần tiếp theo chạy `clean`. Không so sánh một lần build sạch với một lần build tăng dần: khi đó cache hoặc tệp cũ có thể che giấu vấn đề.

### Cách A — Bash (Linux hoặc macOS)

Chạy từ thư mục có `build.xml`:

~~~bash
set -euo pipefail

evidence="../ant-build-evidence"
if [ -e "$evidence/run-1" ] || [ -e "$evidence/run-2" ]; then
    echo "Snapshot đã tồn tại; chọn thư mục evidence mới."
    exit 1
fi
mkdir -p "$evidence"

ant clean dist
cp -R dist "$evidence/run-1"

ant clean dist
cp -R dist "$evidence/run-2"
~~~

Sau đó có hai cây sản phẩm độc lập:

~~~text
ant-build-evidence/
├── run-1/
│   └── demo.jar
└── run-2/
    └── demo.jar
~~~

Lưu ý: `ant clean` chỉ an toàn khi target `clean` của dự án thực sự giới hạn trong đầu ra build. Hãy biết target sẽ xóa những gì; trong ví dụ này nó chỉ xóa `build/` và `dist/`. Thư mục `ant-build-evidence` nằm **ngoài** hai thư mục đó, tránh bị xóa hoặc lọt vào sản phẩm của lượt build thứ hai.

### Cách B — PowerShell (Windows)

~~~powershell
$project = (Get-Location).Path
$evidence = Join-Path (Split-Path -Parent $project) "ant-build-evidence"
$run1 = Join-Path $evidence "run-1"
$run2 = Join-Path $evidence "run-2"

if ((Test-Path $run1) -or (Test-Path $run2)) {
    throw "Snapshot đã tồn tại; chọn thư mục evidence mới."
}
New-Item -ItemType Directory -Path $evidence -Force | Out-Null

ant clean dist
if ($LASTEXITCODE -ne 0) { throw "Build 1 thất bại" }
Copy-Item -LiteralPath (Join-Path $project "dist") -Destination $run1 -Recurse

ant clean dist
if ($LASTEXITCODE -ne 0) { throw "Build 2 thất bại" }
Copy-Item -LiteralPath (Join-Path $project "dist") -Destination $run2 -Recurse
~~~

Với dự án có nhiều tệp xuất bản, hãy sao chép **toàn bộ cây đầu ra**, không chỉ tệp JAR chính. Nếu một lượt thiếu tài nguyên, script so sánh tập tệp ở phần sau sẽ phát hiện.

## 5. Đối chiếu checksum của một sản phẩm

Với hai snapshot đã lưu, tính SHA-256 độc lập:

~~~bash
# Linux (thường có sha256sum)
sha256sum ../ant-build-evidence/run-1/demo.jar
sha256sum ../ant-build-evidence/run-2/demo.jar

# macOS (có sẵn shasum)
shasum -a 256 ../ant-build-evidence/run-1/demo.jar
shasum -a 256 ../ant-build-evidence/run-2/demo.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-FileHash ../ant-build-evidence/run-1/demo.jar -Algorithm SHA256
Get-FileHash ../ant-build-evidence/run-2/demo.jar -Algorithm SHA256
~~~

Lưu ý **so sánh cột digest**, không so sánh cả dòng in ra: đường dẫn `run-1` và `run-2` vốn khác nhau. Ví dụ minh họa:

~~~text
run-1/demo.jar   SHA-256 = 0123...abcd
run-2/demo.jar   SHA-256 = 0123...abcd   => MATCH

run-1/demo.jar   SHA-256 = 0123...abcd
run-2/demo.jar   SHA-256 = 89ab...ef01   => DIFFERENT
~~~

Các chuỗi viết rút gọn phía trên chỉ để giải thích; checksum thật phải có đủ **64 ký tự hexadecimal**. Khi ghi biên bản hoặc kiểm tra tự động, luôn lưu nguyên giá trị, tuyệt đối không so sánh chỉ vài ký tự đầu.

### Dùng chính tác vụ `<checksum>` của Ant

Target `checksum` trong `build.xml` mẫu đã cấu hình:

~~~xml
<checksum file="${dist.dir}/demo.jar"
          algorithm="SHA-256"
          property="demo.sha256"/>
<echo message="demo.jar SHA-256: ${demo.sha256}"/>
~~~

Chạy `ant clean checksum` cho **từng** lượt build và lưu digest cùng snapshot. Ant có thể tạo hoặc xác nhận checksum, nhưng muốn chứng minh tính tái lập thì phải đối chiếu **hai kết quả độc lập**. Không được chỉ chạy target checksum một lần rồi kết luận.

## 6. So sánh toàn bộ cây sản phẩm: đường dẫn + SHA-256

Một tệp `demo.jar` khớp vẫn chưa đủ nếu `dist/` còn chứa `config.properties`, tài liệu, script hay JAR khác. Chuẩn đối chiếu hữu ích là một **manifest**: ánh xạ giữa đường dẫn tương đối và checksum đầy đủ của mỗi tệp.

Ví dụ:

~~~text
app.jar               2c... (SHA-256 đầy đủ)
config/app.properties 8f... (SHA-256 đầy đủ)
scripts/start.sh       71... (SHA-256 đầy đủ)
~~~

Tên tệp phải khớp vì `app.jar` và `old/app.jar` không phải cùng vị trí trong bản phát hành. Sắp xếp tên tệp để kết quả ổn định, rồi so sánh cả **tập tên** lẫn **digest**.

Lưu đoạn sau thành `compare_artifacts.py` (đây là script minh họa dùng Python 3, có thể chạy trên Linux, macOS hoặc Windows):

~~~python
from hashlib import sha256
from pathlib import Path
import sys


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise ValueError(f"Không tìm thấy thư mục sản phẩm: {root}")

    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Chưa hỗ trợ so sánh symbolic link: {path}")
        if path.is_file():
            relative_path = path.relative_to(root).as_posix()
            result[relative_path] = hash_file(path)

    if not result:
        raise ValueError(f"Thư mục sản phẩm không chứa tệp nào: {root}")
    return result


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python compare_artifacts.py RUN1_DIR RUN2_DIR")
        return 2

    try:
        first = build_manifest(Path(sys.argv[1]))
        second = build_manifest(Path(sys.argv[2]))
    except (OSError, ValueError) as error:
        print(f"INPUT_ERROR: {error}", file=sys.stderr)
        return 2

    different = False
    for name in sorted(first.keys() | second.keys()):
        if name not in first:
            print(f"ONLY_RUN_2  {name}  SHA256={second[name]}")
            different = True
        elif name not in second:
            print(f"ONLY_RUN_1  {name}  SHA256={first[name]}")
            different = True
        elif first[name] != second[name]:
            print(f"DIFFERENT   {name}")
            print(f"  run-1 SHA256={first[name]}")
            print(f"  run-2 SHA256={second[name]}")
            different = True
        else:
            print(f"MATCH       {name}  SHA256={first[name]}")

    if different:
        print("RESULT: FAIL - Tập sản phẩm hoặc nội dung byte khác nhau")
        return 1

    print(f"RESULT: PASS - {len(first)} tệp giống nhau theo SHA-256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
~~~

Chạy (trên Windows có thể dùng `py -3` thay `python3`):

~~~bash
python3 compare_artifacts.py +  ../ant-build-evidence/run-1 +  ../ant-build-evidence/run-2
~~~

Script sử dụng ba mã thoát:

| Exit code | Ý nghĩa | Cách dùng trong CI |
| --- | --- | --- |
| `0` | Danh sách tệp và SHA-256 đều khớp | Cho phép bước tiếp theo |
| `1` | Thiếu/thừa tệp hoặc checksum khác | Đánh dấu kiểm tra tái lập thất bại |
| `2` | Sai đầu vào, thư mục rỗng/không tồn tại hoặc lỗi đọc | Sửa cấu hình thí nghiệm |

Script đọc từng khối 1 MiB để không nạp cả JAR lớn vào RAM. Nó chủ ý từ chối symbolic link thay vì âm thầm coi đích liên kết là tệp thường. Nếu sản phẩm có symlink, quyền thực thi, thuộc tính đặc biệt hoặc thư mục rỗng mang ý nghĩa triển khai, phải mở rộng manifest để so sánh những yếu tố đó.

**Ví dụ diễn giải kết quả**:

~~~text
MATCH       demo.jar  SHA256=<64-ký-tự-giống-nhau>
RESULT: PASS - 1 tệp giống nhau theo SHA-256
~~~

hoặc:

~~~text
DIFFERENT   demo.jar
  run-1 SHA256=<digest-1>
  run-2 SHA256=<digest-2>
RESULT: FAIL - Tập sản phẩm hoặc nội dung byte khác nhau
~~~

Từ đây mới xác định **vì sao** một sản phẩm khác nhau, thay vì đoán lỗi ở mã nguồn.

## 7. Khi JAR có checksum khác: so sánh nội dung bên trong

JAR là một dạng ZIP. Cần tách bạch hai phép so sánh:

- **Toàn tệp JAR:** checksum khác nghĩa là có ít nhất một khác biệt ở dạng byte của archive.
- **Payload đã giải nén:** các file `.class`, `META-INF/MANIFEST.MF` và resource bên trong có thể vẫn bằng nhau; khác biệt nằm ở metadata hoặc cách đóng gói.

### Bước 1 — Liệt kê entry

~~~bash
jar tf ../ant-build-evidence/run-1/demo.jar
jar tf ../ant-build-evidence/run-2/demo.jar
~~~

`jar tf` hiển thị tên entry và thứ tự; nó hữu ích để phát hiện tệp thiếu/thừa, nhưng **chưa** cho biết entry nào đổi byte. Nếu có công cụ `unzip`, dùng:

~~~bash
unzip -lv ../ant-build-evidence/run-1/demo.jar
unzip -lv ../ant-build-evidence/run-2/demo.jar
~~~

Danh sách chi tiết giúp quan sát kích thước, thời gian và phương pháp nén (các cột cụ thể tùy bản `unzip`). Metadata archive có thể khác ngay cả khi byte nội dung của từng entry trùng.

### Bước 2 — Giải nén sang hai thư mục mới, rồi so sánh hash

~~~bash
mkdir -p ../ant-build-evidence/unpacked-1
mkdir -p ../ant-build-evidence/unpacked-2

(cd ../ant-build-evidence/unpacked-1 && jar xf ../run-1/demo.jar)
(cd ../ant-build-evidence/unpacked-2 && jar xf ../run-2/demo.jar)

python3 compare_artifacts.py +  ../ant-build-evidence/unpacked-1 +  ../ant-build-evidence/unpacked-2
~~~

Đây là thao tác dành cho artifact **đáng tin cậy** do chính pipeline tạo ra; không giải nén archive không rõ nguồn gốc vào thư mục quan trọng.

**Ba tình huống cần phân biệt:**

1. **JAR hash khác, hash mọi entry sau giải nén giống:** dữ liệu logic trong entry giống nhau; cần kiểm tra timestamp của entry, thứ tự entry, phương pháp/mức nén, thuộc tính ZIP, extra field hoặc metadata archive.
2. **Một entry `.class` khác:** kiểm tra JDK/`javac`, annotation processor, thứ tự đầu vào, mã nguồn sinh, đường dẫn tuyệt đối, hằng số sinh từ thời gian hoặc tham số compiler.
3. **`META-INF/MANIFEST.MF` hay resource khác:** kiểm tra thuộc tính build-time, version tự tăng, đường dẫn máy, giá trị môi trường, charset/line ending, file cấu hình được lọc bằng biến Ant.

Nếu hai JAR có nội dung giải nén giống nhau nhưng byte JAR khác, không nên gọi đó là **bit-for-bit reproducible**. Bản phát hành được vận chuyển là tệp JAR nguyên vẹn, bao gồm cả metadata gói nén.

### Bước 3 — Khoanh vùng nguyên nhân ở build script

Ví dụ một cấu hình có tính không xác định:

~~~xml
<tstamp/>
<jar destfile="${dist.dir}/demo.jar"
     basedir="${build.dir}/classes">
    <manifest>
        <attribute name="Build-Date" value="${DSTAMP}"/>
        <attribute name="Build-Time" value="${TSTAMP}"/>
    </manifest>
</jar>
~~~

`<tstamp>` tạo giá trị dựa trên đồng hồ máy. Nếu hai lượt chạy khác thời điểm, manifest và SHA-256 có thể đổi dù mã nguồn không thay đổi. Trong pipeline cần tái lập, hãy **loại bỏ dữ liệu thay đổi theo thời gian** khỏi sản phẩm, hoặc thay bằng giá trị cố định được suy ra từ đầu vào đã được định nghĩa rõ, chẳng hạn timestamp phát hành chuẩn hóa.

Ngay cả khi manifest không có `Build-Time`, tệp `.class` được tạo mới vẫn có thể mang thời gian sửa đổi mới trên filesystem; khi đóng gói ZIP/JAR, thời gian của entry có thể đi vào archive. Cần xem cấu hình Ant/ZIP thực tế để chuẩn hóa timestamp và thứ tự entry ở khâu đóng gói. Không giả định việc `clean` tự làm cho archive có metadata xác định.

## 8. Bảng chẩn đoán các khác biệt thường gặp

| Dấu hiệu sau hai lần build | Nguyên nhân khả dĩ | Hướng điều tra/sửa |
| --- | --- | --- |
| Cùng tập tên file, JAR hash khác; giải nén ra file giống nhau | Timestamp ZIP, thứ tự entry, phương pháp nén, quyền/extra field | Quan sát `unzip -lv` và công cụ đóng gói; chuẩn hóa metadata trước phát hành |
| `MANIFEST.MF` khác | `<tstamp>`, `Build-Time`, version tự động, đường dẫn máy | Bỏ dữ liệu biến thiên hoặc sinh từ nguồn cố định |
| File `.class` khác | Khác JDK/compiler, generated source, annotation processor, thứ tự đầu vào | Ghi lại `java -version`, khóa phiên bản processor, kiểm tra class bằng `javap -v` |
| File properties, YAML, JSON khác | Lọc biến môi trường, charset, locale, thứ tự sinh dữ liệu | Định nghĩa encoding, sắp xếp đầu vào, bỏ thông tin máy |
| Một run thiếu/thừa tệp | Target không tạo đủ output, file cũ còn lại, điều kiện môi trường | Kiểm tra `clean`, dependency giữa target và điều kiện `if/unless` |
| Chỉ máy A và B cho kết quả khác | Khác OS/JDK/Ant/timezone/line ending, dependency ngoài | So sánh toolchain, biến môi trường và đầu vào đầu cuối |
| SHA khớp nhưng file không chạy trên máy khác | Khác runtime hoặc thành phần triển khai không được đóng gói | Kiểm tra dependency/runtime và phép thử chạy riêng |

Một số mẹo khi kiểm tra:

- Dùng `javap -v -classpath path/to/demo.jar example.Hello` để xem thông tin lớp Java khi nghi ngờ `.class` khác.
- Đối với file văn bản, dùng công cụ diff để thấy dòng thay đổi, đồng thời kiểm tra BOM, newline `CRLF/LF` và encoding.
- Với JAR lồng trong JAR hoặc tài nguyên nhị phân, checksum của entry sẽ chỉ ra tệp con cụ thể khác nhau.
- Một hash khác không cho biết **nguyên nhân**; hãy tìm entry đầu tiên khác, kiểm tra cách nó được sinh ra rồi lặp lại thử nghiệm có kiểm soát.

## 9. Đưa việc đối chiếu vào quy trình CI

Một job kiểm tra tái lập có thể thực hiện chuỗi sau:

~~~text
Checkout một commit cố định
    |
    v
Ghi nhận Ant/JDK/dependency và cấu hình build
    |
    v
ant clean dist  ---> lưu dist thành run-1/
    |
    v
ant clean dist  ---> lưu dist thành run-2/
    |
    v
compare_artifacts.py run-1/ run-2/
    |
    +-- exit 0 --> PASS: lưu manifest/checksum, tiếp tục pipeline
    |
    +-- exit 1 --> FAIL: lưu hai snapshot + khác biệt để phân tích
    |
    +-- exit 2 --> ERROR: kiểm tra lại thư mục/đầu vào của job
~~~

Ở mức cơ bản, các lệnh `ant clean dist` và `python3 compare_artifacts.py ...` có thể được gọi trực tiếp trong CI. Nên cấu hình CI **fail** khi mã thoát khác 0, và lưu bản ghi SHA-256, commit, phiên bản Ant/JDK cùng hai artifact để điều tra.

Để kiểm tra mạnh hơn, thực hiện hai build ở **hai workspace độc lập** từ cùng commit với dependency đã khóa; dùng cùng toolchain trước, sau đó thử trên môi trường khác (nếu mục tiêu là tái lập xuyên máy). Hai lượt chạy trong cùng thư mục có thể vẫn chia sẻ cache ngoài `build/` mà target `clean` không xóa. Bởi vậy, kết quả PASS phải được mô tả kèm phạm vi môi trường và mức độc lập thực tế.

Trong báo cáo có thể ghi:

~~~text
Commit: <git-commit>
Ant: <ant-version>
JDK: <java-version>
Target: clean dist
Snapshot 1: run-1/
Snapshot 2: run-2/
Số tệp được so sánh: <N>
Checksum algorithm: SHA-256
Kết quả: PASS hoặc FAIL
Khác biệt: <đường dẫn + digest tương ứng, nếu có>
~~~

Không nên chỉ ghi “build đã thành công”. Biên bản có đường dẫn và digest cho biết **đã đối chiếu thứ gì**.

## 10. Những sai lầm thường làm phép xác minh mất ý nghĩa

1. **Không chạy `clean`:** lượt thứ hai dùng lại tệp lớp hoặc archive cũ nên kết quả khớp giả tạo.
2. **Chỉ so sánh tên và kích thước:** cùng tên/cùng độ dài vẫn có thể chứa byte khác.
3. **Chỉ hash JAR chính:** bỏ sót resource, script hoặc dependency nằm cạnh JAR trong bản phát hành.
4. **Giải nén và thấy giống nhau rồi tuyên bố hai JAR giống byte:** bỏ qua timestamp, thứ tự ZIP, nén và metadata archive.
5. **Để hai snapshot nằm trong đầu vào của build tiếp theo:** làm thay đổi phạm vi copy, scan tài nguyên hoặc target đóng gói.
6. **Ghi file checksum vào chính `dist/` giữa hai lượt:** tạo thay đổi nhân tạo đối với tập đầu ra.
7. **Dùng hai dependency “cùng phiên bản” nhưng khác byte:** artifact ngoài hoặc snapshot dependency có thể bị thay đổi; khóa nội dung khi cần.
8. **Chỉ so sánh vài ký tự đầu của SHA-256:** dùng digest đầy đủ, và kiểm tra cả tập đường dẫn.
9. **Không kiểm tra mã thoát:** script in `FAIL` nhưng CI vẫn tiếp tục như thể thành công.
10. **Gộp kết luận build tái lập với kết luận chương trình đúng:** phép so sánh sản phẩm và kiểm thử chức năng giải quyết hai câu hỏi khác nhau.

## 11. Bài thực hành có thể tự làm

**Lượt A — Thiết lập đường chuẩn:** tạo dự án mẫu, chạy `ant clean dist` hai lần, lưu `run-1`/`run-2`, so sánh SHA-256 của JAR và chạy script kiểm tra tập tệp. Ghi nhận cả kết quả PASS lẫn FAIL. Nếu FAIL, giải nén JAR và tìm entry khác nhau.

**Lượt B — Cố ý thay đổi một đầu vào:** sửa chuỗi `Hello from Ant` thành `Hello from Ant v2` giữa các lượt, sau đó chạy lại quy trình trên hai snapshot mới. Hash JAR phải khác và hash của `example/Hello.class` sau giải nén cũng sẽ khác. Thí nghiệm này chứng minh công cụ đối chiếu phát hiện được thay đổi thực sự của sản phẩm.

**Lượt C — Điều tra metadata:** trả lại cùng một commit, thêm thuộc tính thời gian vào manifest như ví dụ `<tstamp>`, chạy hai lượt có thời điểm khác nhau. Quan sát xem checksum toàn JAR và nội dung manifest đổi như thế nào. Gỡ trường thời gian, tiếp tục điều tra timestamp/đóng gói nếu archive vẫn khác.

**Lượt D — Mở rộng phạm vi:** thêm file tài nguyên trong `dist/` hoặc tạo hai artifact, rồi xác nhận script bắt được tình huống một run thiếu tệp dù JAR chính trùng checksum.

### Câu hỏi tự kiểm tra kiến thức

- Vì sao hai dòng `BUILD SUCCESSFUL` chưa chứng minh build tái lập?
- Nếu `demo.jar` có SHA-256 khác nhưng mọi entry giải nén giống nhau, nên tìm nguyên nhân ở đâu?
- Tại sao phải so sánh đường dẫn tương đối và toàn bộ cây `dist/`, thay vì chỉ hash một JAR?
- Hai lần clean build cùng máy PASS cho phép khẳng định điều gì, và chưa cho phép khẳng định điều gì?
- Nếu CI gặp `ONLY_RUN_2 config/app.properties`, đây là khác checksum hay khác tập sản phẩm?

**Kết luận:** Một phép xác minh build Ant có thể kiểm chứng được phải giữ nguyên đầu vào, thực hiện hai lượt build sạch, lưu sản phẩm riêng biệt, đối chiếu **tập đường dẫn và SHA-256 đầy đủ**, rồi phân tích nội dung JAR/ZIP khi có khác biệt. Khi tất cả sản phẩm khớp, ta có bằng chứng cụ thể về tính tái lập ở phạm vi đã thử; khi không khớp, manifest và so sánh entry cho biết nơi cần bắt đầu tìm nguyên nhân.
