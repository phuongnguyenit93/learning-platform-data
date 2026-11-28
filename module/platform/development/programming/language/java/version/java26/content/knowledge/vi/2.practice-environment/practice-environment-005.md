# Bật module jdk.incubator.vector khi biên dịch và chạy

Vector API cho phép biểu diễn phép tính trên nhiều phần tử cùng kiểu dưới dạng các lane của một vector. Khi CPU và JVM hỗ trợ, HotSpot có thể biên dịch các phép toán này thành lệnh SIMD phù hợp, giúp xử lý nhiều phần tử trong một lệnh máy. API được cung cấp qua module `jdk.incubator.vector`.

Trong JDK 26, Vector API là **JEP 529 — Eleventh Incubator**. Đến JDK 27, API tiếp tục ở trạng thái **JEP 537 — Twelfth Incubator**. Vì vậy, khi sử dụng trên cả hai phiên bản, bạn vẫn phải chủ động đưa module vào module graph và chấp nhận rằng API có thể thay đổi hoặc bị loại bỏ ở bản JDK tương lai. Bài này dùng cú pháp và công cụ hiện hành của JDK 26/27; hãy biên dịch và chạy bằng đúng JDK mục tiêu của dự án.

## 1. Xác nhận JDK có module Vector API

`jdk.incubator.vector` được phân phối cùng JDK có hỗ trợ Vector API; đây không phải dependency Maven/Gradle cần tải riêng. Tuy nhiên, một runtime image được tạo tối giản có thể đã loại module này.

Trước khi cấu hình dự án, kiểm tra compiler và runtime:

```bash
javac --version
java --version
java --describe-module jdk.incubator.vector
```

Hai lệnh đầu giúp xác nhận phiên bản của compiler và JVM đang được gọi. Lệnh cuối hiển thị descriptor của module nếu module tồn tại trong JDK đang dùng. Kết quả cần nhận diện được tên module `jdk.incubator.vector` và package được export là `jdk.incubator.vector`.

Nếu `java --describe-module` báo không tìm thấy module, hãy kiểm tra `JAVA_HOME`, `PATH` và JDK thực tế đang được IDE/build tool sử dụng. Nếu ứng dụng chạy trên custom runtime image được tạo bằng `jlink`, image đó phải chứa module này; thêm `--add-modules` lúc chạy không thể cài thêm module đã bị loại khỏi image.

## 2. Hiểu `--add-modules` làm gì

Java Platform Module System phân giải các module thành một module graph. Với mã ứng dụng đặt trên classpath, mã thuộc unnamed module. Một module JDK không nhất thiết được đưa vào graph chỉ vì chương trình import một package của nó. Tùy chọn `--add-modules` chỉ định các root module cần phân giải bổ sung.

Với Vector API, tên module cần thêm là:

```text
jdk.incubator.vector
```

Khi biên dịch mã classpath, thêm tùy chọn cho `javac`. Khi chạy ứng dụng classpath, thêm tùy chọn tương ứng cho JVM thông qua lệnh `java`. Hai giai đoạn có cấu hình riêng: compiler cần nhìn thấy module để kiểm tra import và kiểu; runtime cần module trong graph để nạp các lớp được tham chiếu.

`--add-modules` không biến API incubator thành API ổn định, không thay đổi trạng thái JEP và cũng không tự bật một preview feature. Nó chỉ điều khiển việc phân giải module.

## 3. Ứng dụng classpath: cấu hình lúc compile và run

Tạo cấu trúc thư mục đơn giản:

```text
vector-demo/
├── src/
│   └── Main.java
└── out/
```

Nội dung `src/Main.java`:

```java
import java.util.Arrays;

import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorMask;
import jdk.incubator.vector.VectorSpecies;

public class Main {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    static float[] multiply(float[] left, float[] right) {
        if (left.length != right.length) {
            throw new IllegalArgumentException("Array lengths must match");
        }

        float[] result = new float[left.length];

        for (int i = 0; i < left.length; i += SPECIES.length()) {
            VectorMask<Float> mask = SPECIES.indexInRange(i, left.length);
            FloatVector a = FloatVector.fromArray(SPECIES, left, i, mask);
            FloatVector b = FloatVector.fromArray(SPECIES, right, i, mask);
            a.mul(b).intoArray(result, i, mask);
        }

        return result;
    }

    public static void main(String[] args) {
        float[] left = {1, 2, 3, 4, 5};
        float[] right = {10, 20, 30, 40, 50};

        System.out.println(Arrays.toString(multiply(left, right)));
    }
}
```

Ví dụ nhân từng phần tử của hai mảng. `SPECIES_PREFERRED` chọn độ rộng vector được runtime ưu tiên trên nền tảng đang chạy. Vòng lặp tăng chỉ số theo số lane của species; `indexInRange` tạo mask để lượt cuối vẫn xử lý an toàn khi độ dài mảng không chia hết cho số lane. Mask cũng được truyền vào thao tác đọc và ghi mảng để tránh truy cập ngoài giới hạn.

Biên dịch từ thư mục `vector-demo`:

```bash
javac --add-modules jdk.incubator.vector -d out src/Main.java
```

Chạy chương trình:

```bash
java --add-modules jdk.incubator.vector -cp out Main
```

Kết quả:

```text
[10.0, 40.0, 90.0, 160.0, 250.0]
```

Bạn có thể đóng gói các class đã biên dịch thành JAR:

```bash
jar --create --file vector-demo.jar --main-class Main -C out .
java --add-modules jdk.incubator.vector -jar vector-demo.jar
```

> **Điểm cần nhớ:** lệnh `javac` và lệnh `java` đều có `--add-modules jdk.incubator.vector`. Chỉ cấu hình ở một phía có thể khiến biên dịch thành công nhưng chạy lỗi, hoặc ngược lại.

## 4. Ứng dụng dùng named module

Nếu ứng dụng khai báo module riêng bằng `module-info.java`, hãy khai báo quan hệ phụ thuộc bằng `requires`. Khi module ứng dụng được đưa vào graph, module system sẽ phân giải module mà nó yêu cầu.

Cấu trúc mã nguồn:

```text
vector-modular-demo/
└── src/
    └── com.example.vectorapp/
        ├── module-info.java
        └── com/
            └── example/
                └── Main.java
```

Nội dung `src/com.example.vectorapp/module-info.java`:

```java
module com.example.vectorapp {
    requires jdk.incubator.vector;
}
```

Trong `Main.java`, khai báo package và import các lớp Vector API như ví dụ trước:

```java
package com.example;

import jdk.incubator.vector.FloatVector;
import jdk.incubator.vector.VectorSpecies;

public class Main {
    private static final VectorSpecies<Float> SPECIES =
            FloatVector.SPECIES_PREFERRED;

    public static void main(String[] args) {
        FloatVector a = FloatVector.broadcast(SPECIES, 2.0f);
        FloatVector b = FloatVector.broadcast(SPECIES, 3.0f);
        System.out.println(a.mul(b));
    }
}
```

Biên dịch module:

```bash
javac -d out --module-source-path src --module com.example.vectorapp
```

Chạy module:

```bash
java --module-path out --module com.example.vectorapp/com.example.Main
```

Trong trường hợp này, `requires jdk.incubator.vector` đã khai báo dependency ở cấp module. Khi khởi chạy module ứng dụng, module system sẽ phân giải dependency đó. Cách này khác với ứng dụng classpath, nơi bạn cần thêm module bằng `--add-modules`.

## 5. Cấu hình trong build tool

Với dự án dùng classpath, cần truyền tùy chọn cho cả tác vụ biên dịch lẫn JVM chạy ứng dụng và test. Ví dụ dưới đây dùng Gradle Kotlin DSL:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(
        listOf("--add-modules", "jdk.incubator.vector")
    )
}

tasks.withType<JavaExec>().configureEach {
    jvmArgs("--add-modules=jdk.incubator.vector")
}

tasks.withType<Test>().configureEach {
    jvmArgs("--add-modules=jdk.incubator.vector")
}
```

Với Maven, cấu hình compiler plugin để `javac` phân giải module:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <compilerArgs>
            <arg>--add-modules</arg>
            <arg>jdk.incubator.vector</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Nếu test chạy bằng Maven Surefire trên classpath, truyền tùy chọn cho JVM fork:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>--add-modules=jdk.incubator.vector</argLine>
    </configuration>
</plugin>
```

Thiết lập Surefire chỉ áp dụng cho JVM chạy test. Lệnh khởi chạy ứng dụng thực tế, container hoặc service vẫn phải nhận tùy chọn runtime tương ứng nếu chương trình dùng classpath. Nếu ứng dụng là named module, ưu tiên khai báo `requires jdk.incubator.vector` trong `module-info.java` và cấu hình build theo module đó.

Trong IDE, thêm `--add-modules jdk.incubator.vector` vào VM options của Run/Debug Configuration cho ứng dụng classpath. Đồng thời cấu hình compiler/build tool như trên; VM options của Run Configuration không tự động thay thế tùy chọn biên dịch.

## 6. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `package jdk.incubator.vector is not visible` hoặc compiler không truy cập được package | Module chưa được phân giải khi biên dịch mã classpath | Thêm `--add-modules jdk.incubator.vector` vào `javac` hoặc cấu hình `requires` nếu dùng named module |
| `Module jdk.incubator.vector not found` | JDK đang dùng không có module hoặc runtime image đã loại module | Kiểm tra `java --describe-module jdk.incubator.vector`, `JAVA_HOME`, `PATH` và cấu hình JDK của IDE/build tool; tạo lại custom runtime image có module |
| Biên dịch thành công nhưng chạy báo không tìm thấy lớp/module | JVM chạy ứng dụng classpath chưa phân giải module | Thêm `--add-modules jdk.incubator.vector` vào lệnh `java`, VM options, container command hoặc service launcher |
| Máy phát triển chạy được nhưng CI/production lỗi | Compiler và runtime dùng JDK khác nhau hoặc cấu hình build/test/run không đồng nhất | Khóa JDK toolchain/runtime theo phiên bản mục tiêu; cấu hình riêng compile, test và launch |
| Có cảnh báo `using incubating module(s)` hoặc `Using incubator modules` | JDK thông báo chương trình đang dùng API incubator | Đây là cảnh báo trạng thái của API; đọc và đánh giá nó, không mặc định tắt cảnh báo là đã giải quyết vấn đề |

Khi cần kiểm tra nhanh module graph, có thể dùng:

```bash
java --show-module-resolution --add-modules jdk.incubator.vector -cp out Main
```

Tùy chọn `--show-module-resolution` giúp quan sát các module được phân giải khi JVM khởi chạy.

## 7. Lưu ý hiệu năng và tương thích

Vector API biểu diễn SIMD; nó không tự tạo thêm Java thread và không thay thế cơ chế xử lý đồng thời. Một phép toán vector có thể xử lý nhiều lane dữ liệu trong cùng một thao tác, trong khi concurrency thường phối hợp nhiều luồng thực thi.

Không nên giả định cứ dùng Vector API là chương trình nhanh hơn. Khả năng sinh lệnh vector phụ thuộc CPU, kiến trúc, độ rộng vector, JIT compiler và hình dạng phép tính. Nên ưu tiên `SPECIES_PREFERRED`, xử lý phần tử dư bằng mask, benchmark trên phần cứng đích và so sánh với phiên bản scalar tương đương. Tài liệu API nêu rõ có triển khai scalar dự phòng nếu runtime không thể biên dịch thao tác thành lệnh vector.

Vector API vẫn là incubator ở JDK 26 và JDK 27. Module có cùng tên `jdk.incubator.vector`, nhưng trạng thái incubator có nghĩa chữ ký hoặc hành vi API có thể thay đổi giữa các bản JDK. Khi nâng cấp:

1. Đọc JEP và API Specification của JDK đích; không dựa vào số vòng incubator để suy đoán API đã ổn định.
2. Cài đặt và chọn đúng JDK cho compiler, test, IDE, CI và runtime.
3. Biên dịch lại mã trên JDK đích, xử lý cảnh báo hoặc thay đổi API, rồi chạy test và benchmark trên phần cứng triển khai.
4. Nếu đóng gói runtime image tối giản, xác nhận module `jdk.incubator.vector` có trong image.
5. Giữ phần sử dụng Vector API sau một lớp abstraction nội bộ nếu cần khả năng thay thế khi API thay đổi hoặc bị loại bỏ.

Vì API chưa final, tránh để kiểu `jdk.incubator.vector.*` xuất hiện trong API công khai của thư viện mà nhiều ứng dụng khác phải phụ thuộc. Chỉ sử dụng trong phạm vi có kiểm soát khi lợi ích đo được đủ bù chi phí nâng cấp.

## 8. Checklist thực hành

- [ ] `javac --version` và `java --version` trỏ đến JDK mục tiêu.
- [ ] `java --describe-module jdk.incubator.vector` xác nhận module có trong runtime.
- [ ] Với classpath, `javac` có `--add-modules jdk.incubator.vector`.
- [ ] Với classpath, lệnh chạy JVM cũng có `--add-modules jdk.incubator.vector`.
- [ ] Với named module, `module-info.java` khai báo `requires jdk.incubator.vector`.
- [ ] Cấu hình build tool, IDE, test runner và lệnh production đồng nhất.
- [ ] Đã kiểm tra cảnh báo incubator, benchmark và JDK đích trước khi phát hành.

## Tài liệu tham khảo

- [JEP 529 — Vector API (Eleventh Incubator)](https://openjdk.org/jeps/529) — trạng thái và mục tiêu Vector API trong JDK 26.
- [JEP 537 — Vector API (Twelfth Incubator)](https://openjdk.org/jeps/537) — vòng incubator tiếp theo trong JDK 27.
- [JDK 26 API Specification: Module `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/module-summary.html) — module, package và trạng thái incubating.
- [JDK 26 API Specification: Package `jdk.incubator.vector`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.incubator.vector/jdk/incubator/vector/package-summary.html) — ví dụ sử dụng, species, mask và ghi chú hiệu năng.
- [JDK 26 `javac` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — `--add-modules` và cách cấu hình module khi biên dịch.
- [JDK 26 `java` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — tùy chọn module khi chạy ứng dụng.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html) và [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html) — xác nhận Vector API lần lượt là Eleventh và Twelfth Incubator.
