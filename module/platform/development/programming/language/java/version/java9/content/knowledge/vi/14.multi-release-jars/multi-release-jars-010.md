# Kiểm thử từng JDK đích và phát hiện sai khác hành vi

## 1. Vì sao phải kiểm thử trên từng JDK đích?

Một ứng dụng có thể biên dịch thành công nhưng vẫn chạy khác nhau giữa các phiên bản JDK. Khác biệt có thể đến từ bytecode/API được biên dịch, cách runtime chọn lớp trong multi-release JAR, thay đổi của thư viện nền tảng hoặc môi trường chạy như hệ điều hành, locale, charset và TLS provider.

Với multi-release JAR (MR-JAR), việc kiểm thử từng JDK càng quan trọng: cùng một file JAR có thể chứa nhiều implementation của cùng một lớp. JVM sẽ chọn implementation phù hợp với phiên bản runtime đang chạy. Nếu chỉ chạy thử trên JDK dùng để build, ta có thể bỏ sót nhánh code được chọn trên các JDK còn lại.

Cần phân biệt ba phiên bản:

| Phiên bản | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| JDK dùng để build | JDK chạy compiler và công cụ đóng gói. | `javac -version`, `jar --version`. |
| Mức tương thích khi biên dịch | Phiên bản ngôn ngữ, bytecode và API nền tảng mà source được phép sử dụng. | `javac --release N`. |
| JDK dùng khi chạy | JVM thực sự nạp JAR và thực thi ứng dụng. | Chạy bằng `java` của từng JDK đích và ghi nhận `java -version`. |

`--release` giúp kiểm soát đầu ra biên dịch. Nó không thay thế việc chạy thử trên runtime JDK thật.

## 2. Runtime chọn implementation nào trong multi-release JAR?

MR-JAR được nhận diện bằng thuộc tính sau trong manifest của JAR:

```text
Multi-Release: true
```

Cấu trúc của một JAR có implementation nền và implementation riêng cho Java 17 có dạng:

```text
app.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 17/
│           └── com/acme/RuntimeInfo.class
└── com/
    └── acme/
        ├── Main.class
        └── RuntimeInfo.class
```

- Lớp ở thư mục gốc là implementation nền, dùng khi runtime không có phiên bản thay thế phù hợp.
- Lớp trong `META-INF/versions/17/` là implementation dành cho Java 17 trở lên.
- Trên runtime Java 17, JVM chọn lớp ở `versions/17`.
- Trên runtime Java 21 hoặc 25, nếu JAR không có thư mục phiên bản cao hơn, JVM vẫn chọn lớp ở `versions/17`.
- Nếu runtime thấp hơn 17, JVM dùng lớp ở thư mục gốc.

Khi có nhiều thư mục phiên bản, runtime chọn thư mục có số phiên bản cao nhất nhưng không vượt quá feature version của chính runtime. Ví dụ, nếu JAR có các thư mục `9`, `17` và `21`, JDK 17 chọn `17`, JDK 21 chọn `21`, còn JDK 25 cũng chọn `21` nếu không có `25`.

Thuộc tính `Multi-Release: true` là bắt buộc để runtime diễn giải các entry trong `META-INF/versions/` như các phiên bản thay thế. Nếu thiếu thuộc tính này, các entry đó không được dùng theo cơ chế MR-JAR.

Implementation ở các phiên bản khác nhau cần giữ hợp đồng API mà ứng dụng và thư viện phụ thuộc vào. Có thể thay đổi thuật toán bên trong, nhưng không nên để cùng một lời gọi công khai có ý nghĩa hoặc điều kiện lỗi khác nhau ngoài chủ đích đã được đặc tả.

## 3. Tạo một MR-JAR nhỏ để thấy sự khác biệt

Ví dụ này đặt baseline là Java 11 và có một implementation thay thế từ Java 17. Thư mục `src/base` chứa code nền; `src/v17` chứa lớp thay thế có cùng tên đầy đủ.

```text
src/
├── base/com/acme/
│   ├── Main.java
│   └── RuntimeInfo.java
└── v17/com/acme/
    └── RuntimeInfo.java
```

**Implementation nền — `src/base/com/acme/RuntimeInfo.java`:**

```java
package com.acme;

public final class RuntimeInfo {
    private RuntimeInfo() {}

    public static String implementation() {
        return "base implementation";
    }
}
```

**Implementation Java 17 — `src/v17/com/acme/RuntimeInfo.java`:**

```java
package com.acme;

public final class RuntimeInfo {
    private RuntimeInfo() {}

    public static String implementation() {
        return "Java 17+ implementation";
    }
}
```

**Điểm gọi chung — `src/base/com/acme/Main.java`:**

```java
package com.acme;

public final class Main {
    public static void main(String[] args) {
        System.out.println(RuntimeInfo.implementation());
    }
}
```

Biên dịch hai implementation bằng compiler của JDK 17 trở lên:

```powershell
New-Item -ItemType Directory -Force out/base | Out-Null
New-Item -ItemType Directory -Force out/v17/META-INF/versions/17 | Out-Null

javac --release 11 -d out/base src/base/com/acme/RuntimeInfo.java src/base/com/acme/Main.java
javac --release 17 -d out/v17/META-INF/versions/17 -cp out/base src/v17/com/acme/RuntimeInfo.java
```

`--release 11` giới hạn code nền ở API và định dạng class file của Java 11. `--release 17` cho phép implementation thay thế dùng API Java 17. Đường dẫn output của lớp thay thế phải nằm dưới `META-INF/versions/17` trong JAR cuối cùng.

Tạo manifest và đóng gói:

```powershell
$manifest = "Manifest-Version: 1.0`r`nMulti-Release: true`r`n`r`n"
[System.IO.File]::WriteAllText('MANIFEST.MF', $manifest, [System.Text.UTF8Encoding]::new($false))

jar --create --file app.jar --manifest MANIFEST.MF -C out/base . -C out/v17 .
jar --list --file app.jar
```

Trong danh sách entry cần thấy cả `com/acme/RuntimeInfo.class` và `META-INF/versions/17/com/acme/RuntimeInfo.class`. Nếu thiếu entry phiên bản hoặc manifest không có `Multi-Release: true`, JAR không hoạt động theo cấu trúc mong muốn.

Chạy trên JDK 11 sẽ in:

```text
base implementation
```

Chạy cùng file `app.jar` trên JDK 17 trở lên sẽ in:

```text
Java 17+ implementation
```

Ví dụ cố ý giữ nguyên API `RuntimeInfo.implementation()` ở cả hai phiên bản. Lớp `Main` không cần biết implementation nào đang được chọn.

## 4. Kiểm thử cùng một artifact trên từng runtime JDK

Đừng chỉ đổi `JAVA_HOME` rồi build lại ở mỗi job. Hãy build và đóng gói artifact một lần bằng JDK đủ mới cho mọi source set, sau đó phân phối đúng file JAR đó tới các job chạy trên từng JDK đích. Cách này giúp kiểm tra cùng một binary và tránh việc mỗi job vô tình tạo ra một artifact khác nhau.

Ví dụ PowerShell dưới đây chạy cùng `app.jar` trên các JDK được khai báo. Đường dẫn chỉ là ví dụ; thay bằng các thư mục JDK thực tế được cài trên máy hoặc runner:

```powershell
$jdkHomes = @{
    11 = 'C:\jdks\jdk-11'
    17 = 'C:\jdks\jdk-17'
    21 = 'C:\jdks\jdk-21'
    25 = 'C:\jdks\jdk-25'
}

foreach ($target in ($jdkHomes.Keys | Sort-Object)) {
    $java = Join-Path $jdkHomes[$target] 'bin\java.exe'
    if (-not (Test-Path $java)) {
        throw "Missing runtime for JDK $($target): $java"
    }

    $versionLine = & $java -version 2>&1 | Select-Object -First 1
    $featureLine = & $java -XshowSettings:properties -version 2>&1 |
        Select-String 'java.specification.version' | Select-Object -First 1
    $feature = [int](($featureLine.ToString() -split '=')[-1].Trim())
    if ($feature -ne [int]$target) {
        throw "Expected JDK $($target) but executable reports feature $feature"
    }

    $actual = (& $java -cp app.jar com.acme.Main) -join ''
    $expected = if ([int]$target -ge 17) {
        'Java 17+ implementation'
    } else {
        'base implementation'
    }

    if ($actual -ne $expected) {
        throw "JDK $($target) ($versionLine) expected '$expected' but got '$actual'"
    }
    Write-Output "PASS JDK $($target): $actual"
}
```

Chỉ đưa vào ma trận những JDK mà sản phẩm cam kết hỗ trợ. Nếu sản phẩm hỗ trợ nhiều vendor hoặc hệ điều hành, mở rộng ma trận theo các môi trường triển khai thực tế. Một lần chạy trên JDK 25 không chứng minh ứng dụng chạy đúng trên JDK 21; mỗi runtime đích phải được chạy riêng.

## 5. Đưa kiểm thử vào CI

Với dự án có baseline Java 11 và implementation thay thế Java 17, có thể tách pipeline thành hai phần:

1. **Build job:** dùng JDK 17 hoặc mới hơn để biên dịch các source set, tạo MR-JAR và upload artifact.
2. **Runtime test jobs:** mỗi job cài một JDK được hỗ trợ, tải đúng artifact từ build job và chạy smoke test cùng contract/integration tests trên runtime đó.

Ví dụ khung GitHub Actions; `target/app.jar` là đường dẫn artifact do cấu hình build của dự án tạo ra:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - run: ./mvnw -B package
      - uses: actions/upload-artifact@v4
        with:
          name: application-jar
          path: target/app.jar

  runtime-tests:
    needs: build
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        java: ['11', '17', '21', '25']
    steps:
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.java }}
      - uses: actions/download-artifact@v4
        with:
          name: application-jar
          path: artifact
      - name: Run runtime contract tests
        env:
          TARGET_JDK: ${{ matrix.java }}
        run: ./scripts/test-runtime.sh artifact/app.jar
```

Ví dụ script `scripts/test-runtime.sh` cho MR-JAR ở trên:

```bash
#!/usr/bin/env bash
set -euo pipefail

jar_path="${1:?Usage: test-runtime.sh path/to/app.jar}"
actual="$(java -cp "$jar_path" com.acme.Main)"

if [ "$TARGET_JDK" -ge 17 ]; then
  expected='Java 17+ implementation'
else
  expected='base implementation'
fi

if [ "$actual" != "$expected" ]; then
  printf 'Expected: %s\nActual: %s\n' "$expected" "$actual"
  exit 1
fi

printf 'PASS JDK %s: %s\n' "$TARGET_JDK" "$actual"
```

Trong dự án thật, script này nên gọi thêm bộ contract/integration tests dùng cùng artifact. Nếu dự án không dùng Maven, thay lệnh build bằng task đóng gói tương ứng; nguyên tắc giữ nguyên artifact giữa các job vẫn áp dụng.

Nếu implementation dành cho Java 25 được biên dịch bằng `--release 25`, build job phải dùng JDK 25 trở lên. Runtime test jobs vẫn chạy trên từng JDK hỗ trợ, kể cả JDK cũ hơn phiên bản dùng để build.

## 6. Phát hiện sai khác hành vi giữa các JDK

Kiểm thử không nên chỉ xác nhận ứng dụng khởi động. Hãy xác định các hợp đồng quan trọng và chạy cùng bộ kiểm tra trên từng runtime:

- **Lựa chọn implementation:** xác nhận đúng lớp nền hoặc lớp trong `META-INF/versions/N` được sử dụng trên từng JDK.
- **Hợp đồng API:** kết quả, exception được cam kết, quy tắc null, thứ tự dữ liệu và hành vi biên phải nhất quán theo đặc tả của ứng dụng.
- **Serialization và dữ liệu:** kiểm tra đọc dữ liệu cũ, ghi dữ liệu mới, định dạng ngày giờ và tương thích schema nếu sản phẩm có các chức năng này.
- **Đồng thời và hiệu năng:** kiểm tra race condition, timeout, deadlock và ngưỡng hiệu năng quan trọng trên các runtime triển khai.
- **Tích hợp nền tảng:** nếu ứng dụng dùng TLS, chứng thư, DNS, file system hoặc native library, kiểm thử các luồng này trên JDK và hệ điều hành thực tế.

Không bắt buộc mọi implementation phải trả về cùng một chuỗi nội bộ. MR-JAR có thể tối ưu thuật toán theo JDK. Hãy so sánh kết quả theo hợp đồng công khai, đồng thời ghi rõ khác biệt nào là chủ đích và khác biệt nào là regression.

Môi trường cũng có thể làm kết quả lệch nhau. Hãy chủ động đặt charset, locale và timezone khi chúng là một phần của hợp đồng kiểm thử. Ví dụ, dùng `StandardCharsets.UTF_8` thay cho charset mặc định của máy khi đọc/ghi giao thức hoặc file có encoding xác định. Nếu dựa vào timezone mặc định, cùng một instant có thể được hiển thị thành ngày giờ khác nhau giữa runner.

Với mỗi kết quả kiểm thử, lưu tối thiểu phiên bản runtime (`java -version`), vendor, hệ điều hành, tên artifact và checksum artifact. Khi một JDK thất bại, thông tin này giúp tái hiện đúng môi trường và xác định lỗi thuộc runtime, artifact hay cấu hình triển khai.

## 7. Kiểm tra MR-JAR khi có lỗi

Khi JDK chọn nhầm implementation hoặc hành vi khác mong đợi, kiểm tra theo thứ tự:

1. **Manifest:** mở `META-INF/MANIFEST.MF` trong JAR và xác nhận có `Multi-Release: true`.
2. **Entry:** chạy `jar --list --file app.jar`; xác nhận lớp nền và các entry `META-INF/versions/N/` đã được đóng gói đúng vị trí.
3. **Runtime thật:** ghi nhận `java -version` và `java.specification.version` của executable dùng để chạy test; tránh nhầm JDK của build với JDK của runtime.
4. **Phiên bản được chọn:** xác định thư mục phiên bản cao nhất không vượt quá feature version của runtime. Nếu không có thư mục phù hợp, runtime dùng lớp nền.
5. **Mức biên dịch:** kiểm tra lệnh `javac --release` của từng source set và đảm bảo versioned class không gọi API cao hơn mức JDK dự định hỗ trợ.
6. **Artifact:** xác nhận mọi job đang chạy cùng một JAR đã build; không vô tình dùng thư mục `classes` hoặc file JAR cũ từ cache.

Nếu chỉ lỗi trên một JDK, hãy giữ lại artifact và log của job thất bại, rồi chạy lại đúng artifact trong môi trường tương ứng. Không vội sửa code chung trước khi xác định runtime đang nạp implementation nào.

## 8. Checklist phát hành

- Đã xác định rõ baseline và danh sách JDK runtime được hỗ trợ.
- Code nền và từng versioned source set được biên dịch với `--release` phù hợp.
- Manifest có `Multi-Release: true` và JAR chứa đúng entry ở thư mục gốc cùng `META-INF/versions/N/`.
- Cùng một artifact được chạy trên từng JDK đích trong CI.
- Có kiểm tra việc chọn implementation và bộ contract/integration tests trên mỗi runtime.
- Khác biệt hành vi có chủ đích được ghi thành kỳ vọng kiểm thử; regression làm pipeline thất bại.
- Log lưu phiên bản JDK, vendor, hệ điều hành và checksum artifact để có thể tái hiện.

Kiểm thử từng JDK đích giúp xác nhận cả hai mặt của MR-JAR: compiler đã tạo đúng các phiên bản lớp và runtime thực tế đã chọn đúng implementation. `--release` kiểm soát khả năng tương thích khi biên dịch; chỉ việc chạy artifact trên từng JDK được hỗ trợ mới xác nhận được hành vi lúc triển khai.
