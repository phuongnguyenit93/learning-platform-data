# Giới hạn về package, tên lớp và khả năng mở rộng của tệp nguồn gọn

Tệp nguồn gọn (*compact source file*) giúp viết chương trình nhỏ với ít phần khai báo bao quanh. Khi chương trình cần API dùng chung, nhiều package hoặc vòng đời đối tượng phức tạp, hiểu giới hạn của hình thức này sẽ giúp bạn chọn thời điểm chuyển sang lớp khai báo tường minh.

Trong phạm vi học các tính năng Java 22 còn hữu ích ở Java hiện đại, cần phân biệt hai mốc: Java 22 cung cấp **Implicitly Declared Classes and Instance Main Methods** dưới dạng preview của JEP 463; Java 25 chuẩn hóa hướng phát triển này với **Compact Source Files and Instance main Methods** của JEP 512. Các ví dụ thực hành bên dưới lấy **JDK 25 trở lên** làm mốc và không cần bật preview cho tính năng này. Xem [bảng thay đổi ngôn ngữ Java của Oracle](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-summary.html).

## 1. Tệp nguồn gọn vẫn có lớp bao quanh

Lưu ví dụ sau trong `StudyReport.java`:

```java
import java.util.List;

void main() {
    var durations = List.of(45, 30);
    System.out.println("Tong phut hoc: " + totalMinutes(durations));
}

int totalMinutes(List<Integer> durations) {
    return durations.stream().mapToInt(Integer::intValue).sum();
}
```

Chạy bằng JDK 25 trở lên:

```shell
java StudyReport.java
```

Kết quả mong đợi:

```text
Tong phut hoc: 75
```

`main` và `totalMinutes` là thành viên của một lớp cấp cao nhất được khai báo ngầm định. Dòng `import` vẫn được phép. Các phương thức không trở thành hàm toàn cục có thể gọi trực tiếp từ mọi tệp khác. Đây là cấu trúc của một *compact compilation unit*, theo [JLS §7.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3).

Bạn có thể tách một phép tính ra khỏi `main` như trên để dễ đọc. Tuy nhiên, việc có thêm phương thức trợ giúp chưa tạo ra một API có kiểu tên rõ ràng để những thành phần khác sử dụng.

## 2. Giới hạn về package

### Không thêm được package khi giữ nguyên hình thức gọn

Ví dụ sau **không hợp lệ**:

```java
package com.example.learning;

void main() {
    System.out.println("Bao cao hoc tap");
}
```

Cú pháp tệp nguồn gọn không có vị trí cho khai báo `package`. Lớp ngầm định thuộc **unnamed package**, thường được gọi là package mặc định. Muốn dùng `com.example.learning`, bạn cần khai báo lớp bao quanh một cách tường minh.

Chuyển tệp vào thư mục `com/example/learning` cũng không tự tạo khai báo package cho nó. Unnamed package không có package con. Theo mô hình chạy classpath thông thường, đây cũng không phải cách xây dựng package để đưa vào một named module của JPMS. Xem [JLS §7.4.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.4.2).

### Vẫn sử dụng được thư viện có package

Hướng phụ thuộc cần phân biệt là:

```text
Tệp nguồn gọn  ── sử dụng ──>  kiểu public trong package có tên
Mã có package ── gọi API ──>  lớp có tên và package được khai báo rõ
```

Ví dụ đầu dùng `java.util.List` bình thường. Với thư viện bên ngoài, lớp vẫn phải truy cập được và dependency phải có trong cấu hình chạy/biên dịch phù hợp; lệnh `import` không tự tải thư viện.

Ở chiều ngược lại, mã thuộc named package không thể tham chiếu tường minh lớp của unnamed package. Thêm `public` trước một phương thức trong tệp gọn không giải quyết được ranh giới này. Hạn chế đó được giải thích trong [hướng dẫn về lớp khai báo ngầm định của Oracle](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html).

**Hệ quả thiết kế:** nếu công thức tính tổng thời gian học phải được cả ứng dụng web và công cụ dòng lệnh gọi, hãy đặt công thức trong một lớp dịch vụ có package. Tệp gọn có thể làm nơi khởi chạy và gọi lớp đó.

## 3. Giới hạn về tên lớp

### Tên tệp phục vụ công cụ khởi chạy

Với cách triển khai thông thường của JDK, `StudyReport.java` được biên dịch thành lớp mang tên `StudyReport`. Có thể sử dụng hai bước:

```shell
javac StudyReport.java
java StudyReport
```

Lệnh thứ hai chọn lớp ban đầu để khởi chạy. Không viết đuôi `.class` trong lệnh này. Quy ước dùng tên tệp bỏ phần mở rộng để chọn lớp ngầm định được mô tả tại [JLS §12.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1).

Nên đặt tên tệp theo định danh Java dễ đọc, chẳng hạn `StudyReport.java`. Khi đổi tên tệp, hãy cập nhật lệnh chạy, cấu hình IDE và tài liệu liên quan.

### Tên đó không trở thành kiểu để tự tham chiếu

Điểm dễ nhầm là lớp ngầm định vẫn có tên ở mức hệ thống, nhưng khai báo ngầm định của nó có **phạm vi tên rỗng** trong mã nguồn. Không dùng tên tệp như tên kiểu của lớp bao quanh. Quy tắc này nằm tại [JLS §6.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3).

Ví dụ dưới đây **không hợp lệ** nếu `NameDemo.java` là tệp nguồn gọn và không có kiểu `NameDemo` nào khác:

```java
void main() {
    var another = new NameDemo();
}
```

Tương tự, không thiết kế mã theo kiểu `StudyReport report`, `StudyReport.class` hay `StudyReport::someStaticMethod` để tham chiếu lớp ngầm định. Tên được launcher nhận diện không tạo ra một khai báo kiểu tường minh trong chương trình.

Nếu chỉ cần đối tượng đang chạy, vẫn có thể dùng `this` trong phương thức instance. Đây là một ví dụ hợp lệ, cũng lưu riêng trong `NameDemo.java`:

```java
void main() {
    Runnable action = this::printMessage;
    action.run();
    System.out.println(this.getClass().getSimpleName());
}

void printMessage() {
    System.out.println("Dang tao bao cao");
}
```

Với JDK và tên tệp nói trên, kết quả mong đợi là:

```text
Dang tao bao cao
NameDemo
```

`this::printMessage` gắn với một đối tượng sẵn có. `getClass()` quan sát lớp tại thời điểm chạy; nó không tạo một tên kiểu có thể sử dụng trong khai báo biến. Tài liệu Oracle xác nhận khả năng dùng `this` và method reference tới phương thức instance trong [phần tạo tệp nguồn gọn](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html).

Trong một nhóm phát triển, hãy coi việc cần truyền đối tượng của lớp bao quanh qua API là tín hiệu để chuyển sang lớp có tên. Cách này giúp lời gọi, kiểu tham số và trách nhiệm của đối tượng được thể hiện ngay trong mã.

## 4. Giới hạn khi muốn mở rộng lớp bao quanh

Các ràng buộc sau áp dụng cho **lớp ngầm định**, theo [JLS §8.1.8](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.8):

| Nhu cầu | Giới hạn của lớp ngầm định |
| --- | --- |
| Cho lớp khác kế thừa | Lớp là `final` |
| Kế thừa một lớp cha riêng | Lớp cha trực tiếp là `Object` |
| Cho lớp bao quanh implements interface | Không có superinterface trực tiếp |
| Công khai lớp như API | Lớp có package access |
| Tự định nghĩa constructor | Chỉ có constructor mặc định do trình biên dịch tạo |
| Viết khối `{ ... }` hoặc `static { ... }` trực tiếp ở ngoài phương thức | Không được khai báo instance/static initializer cho lớp ngầm định |
| Chỉ chứa các hàm tiện ích | Phải khai báo ít nhất một candidate `main` |

Field initializer vẫn được phép, ví dụ `int defaultMinutes = 25;`. Đây là phần khởi tạo ngay trong khai báo field, khác với một khối initializer đứng riêng.

Một phương thức `private void main()` không phải candidate `main`. Dạng `void main()` dùng trong bài đáp ứng yêu cầu; dạng quen thuộc `public static void main(String[] args)` cũng vẫn dùng được. Điều kiện candidate được quy định tại [JLS §12.1.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4).

### Lớp lồng nhau vẫn có khả năng riêng

Các hạn chế trên không cấm bạn khai báo một lớp thành viên có tên để thực hiện công việc. Ví dụ độc lập sau lưu trong `TaskDemo.java`:

```java
void main() {
    Runnable task = new StudyTask("On tap record");
    task.run();
}

static final class StudyTask implements Runnable {
    private final String title;

    StudyTask(String title) {
        this.title = title;
    }

    @Override
    public void run() {
        System.out.println(title);
    }
}
```

Constructor và `implements Runnable` thuộc `StudyTask`, một lớp được khai báo tường minh. Chúng không thay đổi constructor hoặc interface của lớp bao quanh. Xem quy tắc lớp thành viên tại [JLS §8.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.5).

Ví dụ này phù hợp để gom một tác vụ nội bộ. Nếu `StudyTask` trở thành khái niệm được nhiều thành phần sử dụng, hãy cân nhắc tách nó ra một tệp với package rõ ràng thay vì tiếp tục lồng thêm nhiều trách nhiệm trong điểm khởi chạy.

## 5. Khả năng mở rộng không được quyết định bằng số dòng

Không có một ngưỡng như “quá 100 dòng thì tệp gọn không hợp lệ”. Bạn vẫn có thể thêm field, phương thức và kiểu thành viên; các khai báo kiểu nằm trong tệp gọn là thành viên của lớp ngầm định, không tự trở thành các lớp cấp cao nhất độc lập. Xem [cấu trúc compilation unit](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.3).

Về thiết kế, hãy xem **quan hệ giữa các thành phần**:

| Tình huống | Hướng tổ chức phù hợp |
| --- | --- |
| Bài tập tính toán, chương trình minh họa nhỏ | Giữ tệp gọn, đặt tên rõ cho các hàm trợ giúp |
| Công cụ cá nhân có vài bước xử lý | Có thể giữ điểm khởi chạy gọn và gọi các lớp hỗ trợ |
| Công thức được nhiều ứng dụng gọi | Tách lớp dịch vụ có tên và package |
| Cần tạo nhiều đối tượng với cấu hình khác nhau | Khai báo lớp và constructor tường minh |
| Cần tổ chức API, package hoặc named module | Chuyển phần liên quan sang cấu trúc lớp/package rõ ràng |
| Muốn kiểm thử nghiệp vụ độc lập với việc chạy chương trình | Đưa nghiệp vụ vào lớp có thể khởi tạo và gọi trực tiếp |

Đây là các tiêu chí lựa chọn kiến trúc, không phải giới hạn hiệu năng hoặc số lượng tệp do tính năng áp đặt. Một chương trình có điểm khởi chạy gọn vẫn có thể gọi nhiều lớp khác. Ngược lại, chỉ bọc hàng trăm dòng vào `class App` cũng chưa giúp phân chia trách nhiệm tốt hơn.

Trong ví dụ báo cáo học tập, dấu hiệu nên tách lớp là việc tổng thời gian phải được tính cho cả báo cáo CLI và một màn hình khác, hoặc cần truyền dữ liệu/cấu hình qua constructor. Việc thêm một dòng in kết quả thường chưa tạo ra nhu cầu đó.

## 6. Chuyển ví dụ sang lớp có tên và package

Mục tiêu là đưa phép tính vào một thành phần dùng lại được, đồng thời giữ điểm khởi chạy dễ đọc. Các đoạn mã dưới đây là nội dung minh họa cho hai tệp mới khi người học thực hành.

Cấu trúc thư mục:

```text
src/
└── com/
    └── example/
        └── learning/
            ├── StudyReport.java
            └── StudySummary.java
```

Nội dung `src/com/example/learning/StudySummary.java`:

```java
package com.example.learning;

import java.util.List;

public final class StudySummary {
    public int totalMinutes(List<Integer> durations) {
        return durations.stream().mapToInt(Integer::intValue).sum();
    }
}
```

Nội dung `src/com/example/learning/StudyReport.java`:

```java
package com.example.learning;

import java.util.List;

public class StudyReport {
    void main() {
        var summary = new StudySummary();
        var durations = List.of(45, 30);
        System.out.println("Tong phut hoc: " + summary.totalMinutes(durations));
    }
}
```

Ví dụ giả định danh sách và phần tử đều khác `null`, các giá trị là số phút nhỏ, không âm. Quy tắc kiểm tra dữ liệu đầu vào có thể được bổ sung trong `StudySummary` tùy yêu cầu thực tế.

Ở thư mục chứa `src`, chạy bằng JDK 25 trở lên:

```shell
javac -d out src/com/example/learning/StudySummary.java src/com/example/learning/StudyReport.java
java -cp out com.example.learning.StudyReport
```

Kết quả mong đợi vẫn là:

```text
Tong phut hoc: 75
```

Sau chuyển đổi, chương trình có ba điểm khác biệt về cấu trúc:

1. `StudyReport` là lớp được khai báo rõ, thuộc `com.example.learning`.
2. `StudySummary` có tên kiểu dùng được trong khai báo tham số, biến và lời gọi constructor; mã ở package khác có thể dùng API `public` này khi dependency và quyền truy cập cho phép.
3. Phép tính có thể được gọi trực tiếp trong kiểm thử hoặc một điểm khởi chạy khác, không cần chạy `main` để lấy kết quả.

`void main()` vẫn hợp lệ trong **lớp có tên** trên JDK 25 trở lên. Instance main không phụ thuộc vào việc có bỏ khai báo lớp hay không; quy tắc khởi chạy được mô tả tại [JLS §12.1.4](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.1.4). Với lớp có tên dùng instance main, cần bảo đảm việc tạo đối tượng lúc khởi chạy đáp ứng quy tắc của launcher; ví dụ trên dùng constructor mặc định.

Ví dụ biên dịch chọn tường minh lớp ban đầu bằng tên đầy đủ trong lệnh `java -cp`. Đây là cách khởi chạy từ classpath được mô tả trong [tài liệu lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

### Có thể giữ tệp gọn làm điểm khởi chạy

Nếu chỉ muốn tái sử dụng nghiệp vụ, bạn không bắt buộc chuyển toàn bộ chương trình cùng lúc. Sau khi biên dịch `StudySummary` vào `out`, một `QuickReport.java` riêng vẫn có thể viết:

```java
import com.example.learning.StudySummary;
import java.util.List;

void main() {
    var summary = new StudySummary();
    System.out.println(summary.totalMinutes(List.of(45, 30)));
}
```

Chạy ở thư mục có `QuickReport.java` và `out`:

```shell
java --class-path out QuickReport.java
```

Kết quả mong đợi là `75`. Ở chế độ chạy tệp nguồn, classpath cung cấp lớp hỗ trợ đã biên dịch; xem [source-file mode của lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

Lựa chọn này hữu ích khi nhiều công cụ nhỏ cùng gọi một thư viện chung: mỗi công cụ giữ phần điều phối ngắn, còn nghiệp vụ có nơi định nghĩa và kiểm thử riêng.

## 7. Những nhầm lẫn cần tránh

- **“Không viết class thì chương trình không có lớp.”** Các thành viên vẫn thuộc lớp ngầm định; đây không phải mô hình hàm toàn cục.
- **“Có thể thêm package ở đầu rồi giữ nguyên các hàm.”** Muốn khai báo package, hãy thêm lớp bao quanh và chuyển sang compilation unit thông thường.
- **“Chạy được java StudyReport thì gọi new StudyReport() được.”** Tên chọn lớp của launcher và phạm vi tên kiểu trong mã nguồn là hai cơ chế khác nhau.
- **“Thêm public vào main sẽ biến lớp thành API công khai.”** Phạm vi truy cập của phương thức không thay đổi cấu trúc và package của lớp bao quanh.
- **“Chuyển sang lớp có tên là phải bỏ instance main.”** Trên mốc Java 25, bạn có thể tiếp tục dùng instance main với lớp có tên.

## 8. Áp dụng cho báo cáo học tập

Với một bài tập chỉ nhập danh sách thời lượng rồi in tổng, `StudyReport.java` dạng gọn là đủ. Khi cùng phép tính được dùng ở nhiều nơi, đưa nó vào `StudySummary` có package giúp người gọi biết phải tạo đối tượng nào và gọi phương thức nào. Khi đối tượng cần constructor, interface hoặc quan hệ kế thừa riêng, khai báo lớp tường minh cho thành phần đó.

Cách phát triển này giữ lại lợi ích khởi đầu đơn giản của tính năng được preview trong Java 22, đồng thời sử dụng hình thức đã chuẩn hóa để tiếp tục phát triển trên Java hiện đại.