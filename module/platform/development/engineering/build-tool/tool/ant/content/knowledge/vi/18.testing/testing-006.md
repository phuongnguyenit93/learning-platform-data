# Tách kiểm thử đơn vị và kiểm thử tích hợp trong đồ thị target

Trong Apache Ant, các bước build được tổ chức thành những `target` có quan hệ phụ thuộc. Với một dự án Java, kiểm thử đơn vị (*unit test*) và kiểm thử tích hợp (*integration test*) thường dùng chung mã nguồn ứng dụng đã biên dịch nhưng có mục đích, dữ liệu, dependency và môi trường chạy khác nhau. Nếu gom tất cả vào một target duy nhất, mỗi lần kiểm tra nhanh cũng có thể phải khởi tạo dịch vụ ngoài, kết nối database hoặc chạy một tập kiểm thử dài.

Tách hai loại kiểm thử thành các target riêng giúp kiểm soát chính xác đồ thị thực thi: target unit test chỉ phụ thuộc vào mã ứng dụng và thư viện kiểm thử cần thiết; target integration test có thêm bước chuẩn bị môi trường và dependency tích hợp. Một target tổng hợp có thể gọi cả hai khi cần chạy toàn bộ bộ kiểm thử.

## 1. Phân biệt unit test và integration test

Unit test kiểm tra một đơn vị nhỏ của chương trình, thường là một lớp hoặc một thành phần, với các dependency được thay thế bằng stub, fake hoặc mock khi phù hợp. Mục tiêu là kiểm tra logic nhanh, ổn định và ít phụ thuộc vào môi trường bên ngoài.

Integration test kiểm tra sự phối hợp giữa nhiều thành phần hoặc giữa ứng dụng với hệ thống bên ngoài, chẳng hạn database, message broker, filesystem, HTTP service hoặc một module khác. Các kiểm thử này có thể cần cấu hình, dữ liệu mẫu, credentials, container hoặc dịch vụ đang chạy.

| Tiêu chí | Unit test | Integration test |
|---|---|---|
| Phạm vi | Một đơn vị hoặc một lớp | Nhiều thành phần phối hợp |
| Dependency | Thường được thay thế hoặc cô lập | Thường dùng dependency thật hoặc môi trường gần thực tế |
| Thời gian chạy | Thường ngắn | Thường dài hơn |
| Môi trường | Có thể chạy ngay trên máy phát triển hoặc CI | Có thể cần database, service hoặc cấu hình riêng |
| Dữ liệu | Nhỏ, độc lập, dễ tạo lại | Có thể cần fixture, schema hoặc dữ liệu tích hợp |
| Tần suất | Có thể chạy sau mỗi thay đổi nhỏ | Thường chạy ở bước kiểm tra sâu hơn hoặc theo lịch |

Hai loại kiểm thử bổ sung cho nhau. Unit test giúp phát hiện lỗi logic gần vị trí gây lỗi; integration test phát hiện vấn đề về giao tiếp, cấu hình, schema, serialization hoặc cách các thành phần kết hợp.

## 2. Đặt source root và output riêng cho từng loại test

Một cách tổ chức rõ ràng là tách mã ứng dụng, unit test và integration test thành các source root riêng:

```text
project/
├── build.xml
├── src/
│   ├── main/java/             # Mã ứng dụng
│   └── test/
│       ├── unit/java/         # Unit test
│       └── integration/java/  # Integration test
├── lib/
│   ├── test/                  # JUnit và thư viện test
│   └── integration/           # Driver hoặc client tích hợp
└── build/
    ├── classes/main/          # Bytecode ứng dụng
    ├── classes/unit/          # Bytecode unit test
    ├── classes/integration/   # Bytecode integration test
    └── reports/
        ├── unit/
        └── integration/
```

Tách thư mục nguồn giúp Ant chọn đúng lớp cho từng loại kiểm thử. Tách thư mục class output còn giúp tránh trường hợp một target vô tình chạy các lớp test thuộc nhóm khác.

Ví dụ, `src/test/unit/java/com/example/PriceCalculatorTest.java` thuộc unit test, còn `src/test/integration/java/com/example/OrderRepositoryIT.java` thuộc integration test. Hai lớp có thể cùng kiểm tra package `com.example`, nhưng được biên dịch vào hai output root khác nhau.

## 3. Đồ thị target cho hai loại kiểm thử

Một đồ thị điển hình có thể được tổ chức như sau:

```text
                    compile-main
                    /          \
                   v            v
             compile-unit   compile-integration
                   |            |
                   v            v
              run-unit      prepare-integration
                                |
                                v
                         run-integration

              test-unit       test-integration
                   \             /
                    v           v
                       test-all
```

Trong buildfile thực tế, target `run-unit` phụ thuộc `compile-unit`; target `run-integration` phụ thuộc cả `compile-integration` và `prepare-integration`. `test-unit` và `test-integration` là các điểm gọi rõ ràng cho từng nhóm; `test-all` tổng hợp cả hai.

Các nguyên tắc tổ chức quan trọng:

- Cả hai nhóm kiểm thử có thể dùng chung target `compile-main` để biên dịch mã ứng dụng.
- Unit test không phụ thuộc target chuẩn bị database hoặc dịch vụ tích hợp.
- Integration test phụ thuộc bước chuẩn bị môi trường mà nó cần.
- Target tổng hợp chỉ được gọi khi người dùng muốn chạy cả hai nhóm.
- Một target nên có trách nhiệm rõ ràng: biên dịch, chuẩn bị môi trường hoặc chạy một nhóm test.

Ant xử lý các target trong `depends` trước target hiện tại. Một target dependency được gọi nhiều lần trong cùng một lần chạy build chỉ thực thi một lần. Vì vậy, nếu unit và integration test cùng phụ thuộc `compile-main`, Ant không cần biên dịch mã ứng dụng hai lần trong cùng invocation.

## 4. Tạo classpath riêng cho từng nhóm test

Mã kiểm thử thường cần các lớp ứng dụng đã biên dịch và thư viện JUnit. Integration test có thể cần thêm driver database hoặc client của dịch vụ ngoài.

Ví dụ khai báo các Path:

```xml
<path id="main.compile.classpath">
    <fileset dir="lib">
        <include name="*.jar" />
    </fileset>
</path>

<path id="unit.test.classpath">
    <pathelement location="build/classes/main" />
    <pathelement location="build/classes/unit" />
    <fileset dir="lib/test">
        <include name="*.jar" />
    </fileset>
</path>

<path id="integration.test.classpath">
    <pathelement location="build/classes/main" />
    <pathelement location="build/classes/integration" />
    <fileset dir="lib/test">
        <include name="*.jar" />
    </fileset>
    <fileset dir="lib/integration">
        <include name="*.jar" />
    </fileset>
</path>
```

`main.compile.classpath` cung cấp dependency để biên dịch ứng dụng. `unit.test.classpath` chứa mã ứng dụng, mã unit test và thư viện kiểm thử. `integration.test.classpath` bổ sung thư viện cần để kết nối hệ thống ngoài.

Trong dự án thực tế, nên khai báo dependency chính xác theo từng nhóm thay vì đưa tất cả JAR trong repository vào mọi classpath. Classpath quá rộng có thể gây xung đột phiên bản và khiến unit test vô tình phụ thuộc vào thư viện chỉ dành cho integration test.

## 5. Tách target biên dịch

Target `compile-main` biên dịch mã ứng dụng vào output root dùng chung:

```xml
<target name="compile-main">
    <mkdir dir="build/classes/main" />

    <javac
        srcdir="src/main/java"
        destdir="build/classes/main"
        classpathref="main.compile.classpath"
        encoding="UTF-8"
        includeantruntime="false" />
</target>
```

Unit test biên dịch vào output riêng và nhìn thấy class của ứng dụng:

```xml
<target name="compile-unit" depends="compile-main">
    <mkdir dir="build/classes/unit" />

    <javac
        srcdir="src/test/unit/java"
        destdir="build/classes/unit"
        classpathref="unit.test.classpath"
        encoding="UTF-8"
        includeantruntime="false" />
</target>
```

Integration test cũng có target biên dịch riêng:

```xml
<target name="compile-integration" depends="compile-main">
    <mkdir dir="build/classes/integration" />

    <javac
        srcdir="src/test/integration/java"
        destdir="build/classes/integration"
        classpathref="integration.test.classpath"
        encoding="UTF-8"
        includeantruntime="false" />
</target>
```

Hai target biên dịch test cùng phụ thuộc `compile-main`, nhưng mỗi target chỉ lấy nguồn từ thư mục tương ứng. Nhờ đó, việc chạy unit test không cần biên dịch lớp integration test và ngược lại.

## 6. Chạy unit test độc lập

Ant cung cấp task `junit` thông qua phần tích hợp JUnit. Cần bảo đảm phiên bản Ant có task JUnit tương ứng và thư viện JUnit cùng dependency của nó nằm trên classpath phù hợp.

Ví dụ target chạy unit test:

```xml
<target name="run-unit" depends="compile-unit">
    <mkdir dir="build/reports/unit" />

    <junit
        fork="true"
        haltonfailure="true"
        printsummary="yes">

        <classpath refid="unit.test.classpath" />
        <formatter type="plain" />

        <batchtest todir="build/reports/unit">
            <fileset dir="src/test/unit/java">
                <include name="**/*Test.java" />
            </fileset>
        </batchtest>
    </junit>
</target>

<target name="test-unit" depends="run-unit" />
```

`batchtest` tìm các lớp test theo mẫu trong source root. Classpath của JUnit phải chứa class ứng dụng, class unit test và thư viện test cần thiết. `fork="true"` chạy bộ test trong JVM riêng, giúp giảm tác động của trạng thái JVM test tới tiến trình Ant. `haltonfailure="true"` làm build thất bại nếu có test thất bại.

Khi chạy:

```shell
ant test-unit
```

Ant biên dịch mã ứng dụng, biên dịch unit test rồi chỉ chạy các lớp khớp `**/*Test.java`. Target này không phụ thuộc vào bước chuẩn bị integration environment.

## 7. Chuẩn bị môi trường cho integration test

Integration test có thể cần một database, một dịch vụ HTTP, một broker hoặc dữ liệu fixture. Các điều kiện này nên được biểu diễn bằng target riêng để dependency của integration test thể hiện rõ.

Ví dụ, trước khi chạy test, kiểm tra file cấu hình môi trường đã tồn tại:

```xml
<property name="integration.config" value="config/integration.properties" />

<target name="prepare-integration">
    <available
        file="${integration.config}"
        property="integration.config.present" />

    <fail
        unless="integration.config.present"
        message="Missing integration configuration: ${integration.config}" />

    <mkdir dir="build/reports/integration" />
</target>
```

Target này xác nhận cấu hình đã có và chuẩn bị thư mục báo cáo. Trong dự án thực tế, có thể mở rộng nó để tạo schema, nạp fixture hoặc gọi script khởi động môi trường test. Nếu database hoặc service được cung cấp bởi CI, target có thể kiểm tra endpoint hoặc cấu hình kết nối thay vì tự khởi động dịch vụ.

Không nên đặt bước chuẩn bị tích hợp trong `compile-main` hoặc `compile-unit`. Làm như vậy khiến những target biên dịch và unit test phải phụ thuộc môi trường ngoài dù chúng không cần đến môi trường đó.

## 8. Chạy integration test độc lập

Target chạy integration test phụ thuộc cả bước biên dịch và chuẩn bị môi trường:

```xml
<target name="run-integration"
        depends="compile-integration,prepare-integration">

    <junit
        fork="true"
        haltonfailure="true"
        printsummary="yes">

        <classpath refid="integration.test.classpath" />
        <sysproperty
            key="integration.config"
            value="${integration.config}" />
        <formatter type="plain" />

        <batchtest todir="build/reports/integration">
            <fileset dir="src/test/integration/java">
                <include name="**/*IT.java" />
            </fileset>
        </batchtest>
    </junit>
</target>

<target name="test-integration" depends="run-integration" />
```

Các lớp có hậu tố `IT` được chọn riêng bằng mẫu `**/*IT.java`. System property `integration.config` được truyền vào JVM chạy test để mã kiểm thử biết file cấu hình kết nối.

Ví dụ đọc cấu hình trong test:

```java
public class OrderRepositoryIT {
    @org.junit.Test
    public void canReadPersistedOrder() {
        String config = System.getProperty("integration.config");
        if (config == null) {
            throw new IllegalStateException("Missing integration.config");
        }

        // Đọc cấu hình kết nối và kiểm tra tương tác với repository.
    }
}
```

Đoạn mã chỉ minh họa cách nhận cấu hình. Test thực tế cần khởi tạo và đóng kết nối, chuẩn bị dữ liệu và làm sạch fixture theo vòng đời của framework kiểm thử.

Khi chạy:

```shell
ant test-integration
```

Ant biên dịch mã ứng dụng, biên dịch integration test, kiểm tra cấu hình và chạy các lớp `*IT`. Nếu bước chuẩn bị thất bại, target chạy test không được thực thi.

## 9. Tạo target tổng hợp mà không làm unit test phụ thuộc integration test

Có thể tạo target chạy từng nhóm hoặc chạy tất cả:

```xml
<target name="test-all" depends="test-unit,test-integration" />
```

Các lệnh gọi có ý nghĩa khác nhau:

```shell
# Chạy nhanh unit test
ant test-unit

# Chạy riêng integration test
ant test-integration

# Chạy cả hai nhóm
ant test-all
```

Không nên đặt `test-integration` làm dependency của `test-unit` nếu mục tiêu là giữ unit test nhanh và độc lập. Tương tự, target `compile-main` không nên phụ thuộc vào target chuẩn bị database.

Trong một dự án, target mặc định có thể là `test-unit` hoặc `compile`, tùy quy trình của nhóm. Integration test vẫn có thể được gọi trực tiếp hoặc được đưa vào pipeline CI ở giai đoạn kiểm tra sâu hơn.

## 10. Hiểu thứ tự dependency và hành vi khi lỗi

Ant xử lý các target trong thuộc tính `depends` trước khi thực thi phần thân target hiện tại. Danh sách dependency được xử lý theo thứ tự khai báo; target đã chạy trong cùng invocation sẽ không chạy lại.

Ví dụ:

```xml
<target name="test-integration"
        depends="compile-integration,prepare-integration,run-integration" />
```

Khi gọi `ant test-integration`, Ant xử lý `compile-integration`, sau đó `prepare-integration`, rồi `run-integration`. Nếu `prepare-integration` thất bại, các bước phía sau không được chạy.

Điều kiện `if` và `unless` trên một target chỉ điều khiển phần thân của target đó. Các dependency vẫn được xử lý trước khi Ant xét điều kiện. Vì vậy, nếu gắn `unless="skip.integration"` lên target tổng hợp mà các dependency của nó cần được bỏ qua, các dependency vẫn có thể chạy. Với unit test và integration test, việc tạo hai target gọi tường minh thường dễ hiểu hơn việc dựa vào một cờ điều kiện đặt trên target cha.

Một điểm khác cần lưu ý là target dependency không phải khối `finally`. Nếu integration test thất bại, target teardown được đặt sau nó trong danh sách dependency có thể không chạy. Với dịch vụ cần dừng chắc chắn sau test, hãy dùng cơ chế teardown của framework kiểm thử, script điều phối có xử lý finally, hoặc pipeline CI có bước cleanup luôn được thực hiện. Không nên giả định Ant tự chạy mọi dependency còn lại sau khi một target thất bại.

## 11. Dữ liệu kiểm thử và tính độc lập giữa hai nhóm

Unit test và integration test nên có dữ liệu riêng phù hợp với phạm vi của chúng.

Với unit test:

- Tạo dữ liệu nhỏ ngay trong test hoặc dùng fixture đơn giản.
- Tránh phụ thuộc vào database đang chạy trên máy phát triển.
- Dùng mock/fake cho hệ thống ngoài khi mục tiêu là kiểm tra logic của một lớp.
- Bảo đảm mỗi test có thể chạy độc lập và theo thứ tự bất kỳ.

Với integration test:

- Dùng database/schema hoặc namespace test riêng.
- Khởi tạo dữ liệu trước khi kiểm tra và dọn dữ liệu sau đó.
- Đưa endpoint, credentials và cấu hình môi trường vào property hoặc file cấu hình, không hardcode trong mã nguồn.
- Đảm bảo nhiều lần chạy test không phụ thuộc vào dữ liệu còn sót lại từ lần trước.
- Đặt timeout hợp lý cho thao tác mạng hoặc dịch vụ có thể treo.

Nếu một lớp tiện ích được dùng chung bởi cả hai nhóm, có thể đặt nó trong source root test chung rồi đưa output của source root đó vào cả hai classpath. Tuy nhiên, cần giữ rõ ranh giới: unit test không nên vô tình kéo theo dependency tích hợp chỉ vì một lớp tiện ích dùng chung import chúng.

## 12. Ví dụ buildfile hoàn chỉnh

Buildfile dưới đây minh họa cấu trúc target tách biệt. Giả sử JUnit và các dependency test đã được đặt trong `lib/test`, còn driver tích hợp nằm trong `lib/integration`.

```xml
<project name="separated-tests" default="test-unit">

    <property name="main.src" value="src/main/java" />
    <property name="unit.src" value="src/test/unit/java" />
    <property name="integration.src" value="src/test/integration/java" />

    <property name="main.classes" value="build/classes/main" />
    <property name="unit.classes" value="build/classes/unit" />
    <property name="integration.classes" value="build/classes/integration" />
    <property name="integration.config" value="config/integration.properties" />

    <path id="main.compile.classpath">
        <fileset dir="lib">
            <include name="*.jar" />
        </fileset>
    </path>

    <path id="unit.test.classpath">
        <pathelement location="${main.classes}" />
        <pathelement location="${unit.classes}" />
        <fileset dir="lib/test">
            <include name="*.jar" />
        </fileset>
    </path>

    <path id="integration.test.classpath">
        <pathelement location="${main.classes}" />
        <pathelement location="${integration.classes}" />
        <fileset dir="lib/test">
            <include name="*.jar" />
        </fileset>
        <fileset dir="lib/integration">
            <include name="*.jar" />
        </fileset>
    </path>

    <target name="clean">
        <delete dir="build" />
    </target>

    <target name="compile-main">
        <mkdir dir="${main.classes}" />
        <javac srcdir="${main.src}"
               destdir="${main.classes}"
               classpathref="main.compile.classpath"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="compile-unit" depends="compile-main">
        <mkdir dir="${unit.classes}" />
        <javac srcdir="${unit.src}"
               destdir="${unit.classes}"
               classpathref="unit.test.classpath"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="compile-integration" depends="compile-main">
        <mkdir dir="${integration.classes}" />
        <javac srcdir="${integration.src}"
               destdir="${integration.classes}"
               classpathref="integration.test.classpath"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="run-unit" depends="compile-unit">
        <mkdir dir="build/reports/unit" />
        <junit fork="true" haltonfailure="true" printsummary="yes">
            <classpath refid="unit.test.classpath" />
            <formatter type="plain" />
            <batchtest todir="build/reports/unit">
                <fileset dir="${unit.src}">
                    <include name="**/*Test.java" />
                </fileset>
            </batchtest>
        </junit>
    </target>

    <target name="test-unit" depends="run-unit" />

    <target name="prepare-integration">
        <available file="${integration.config}"
                   property="integration.config.present" />
        <fail unless="integration.config.present"
              message="Missing integration configuration: ${integration.config}" />
        <mkdir dir="build/reports/integration" />
    </target>

    <target name="run-integration"
            depends="compile-integration,prepare-integration">
        <junit fork="true" haltonfailure="true" printsummary="yes">
            <classpath refid="integration.test.classpath" />
            <sysproperty key="integration.config"
                         value="${integration.config}" />
            <formatter type="plain" />
            <batchtest todir="build/reports/integration">
                <fileset dir="${integration.src}">
                    <include name="**/*IT.java" />
                </fileset>
            </batchtest>
        </junit>
    </target>

    <target name="test-integration" depends="run-integration" />
    <target name="test-all" depends="test-unit,test-integration" />

</project>
```

Một số lệnh sử dụng:

```shell
# Chạy mặc định: chỉ unit test
ant

# Chỉ chạy unit test
ant test-unit

# Chỉ chạy integration test (cần môi trường và file cấu hình)
ant test-integration

# Chạy cả hai nhóm
ant test-all

# Xóa output và báo cáo cũ
ant clean
```

Ví dụ dùng `junit` giả định phần tích hợp JUnit của Ant đã sẵn sàng và các JAR JUnit cần thiết có trong thư mục được tham chiếu. Tùy phiên bản Ant/JUnit, cần cài đặt đúng task adapter và phiên bản JUnit tương thích. Mã kiểm thử tích hợp cũng cần một database hoặc service đã được cung cấp; target kiểm tra file cấu hình không tự khởi động những dịch vụ đó.

## 13. Lỗi thường gặp khi tổ chức đồ thị test

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Chạy unit test nhưng Ant vẫn chuẩn bị database | Unit target phụ thuộc vào target integration hoặc target tổng hợp sai | Bỏ dependency tích hợp khỏi nhánh unit |
| Unit test chạy cả lớp integration test | Hai nhóm dùng chung thư mục nguồn và mẫu chọn quá rộng | Tách source root hoặc dùng include riêng như `*Test.java` và `*IT.java` |
| Integration test không tìm thấy driver hoặc client | Thiếu JAR trong classpath tích hợp | Bổ sung dependency vào `integration.test.classpath` |
| Test compile không tìm thấy lớp ứng dụng | Classpath thiếu output của `compile-main` | Thêm `${main.classes}` vào classpath test |
| Test chạy nhưng không tìm thấy cấu hình | Chưa chuẩn bị file hoặc chưa truyền property vào JVM test | Đưa kiểm tra vào `prepare-integration` và truyền `<sysproperty>` |
| Chạy `test-all` nhưng compile-main bị lặp | Các target có cách gọi hoặc cấu hình build không cùng invocation | Đưa các nhánh về cùng dependency `compile-main`; Ant chỉ chạy target một lần mỗi invocation |
| Dữ liệu còn lại làm lần test sau thất bại | Fixture không được dọn hoặc test dùng chung schema | Tạo dữ liệu cô lập và cleanup trong framework/CI |
| Dịch vụ vẫn chạy sau khi integration test lỗi | Cleanup được mô hình hóa như dependency đứng sau test | Dùng finally/teardown của framework hoặc cleanup bảo đảm trong CI |
| Đặt `unless` trên target cha nhưng dependency vẫn chạy | Ant xử lý dependency trước khi xét điều kiện của target cha | Dùng target riêng để gọi rõ từng nhóm hoặc đặt điều kiện ở đúng các bước cần điều khiển |

Khi debug, hãy xem target nào đã được gọi và lần theo cạnh `depends` từ target được yêu cầu. Sau đó xác định source root, output root, classpath và điều kiện môi trường của nhóm test tương ứng. Đồ thị rõ ràng giúp tìm ra vì sao một bước không mong muốn lại được thực thi.

## 14. Quy trình thiết kế đồ thị kiểm thử

Khi tách unit test và integration test trong Ant, có thể tiến hành theo trình tự sau:

1. Phân loại các lớp kiểm thử theo dependency và môi trường cần thiết.
2. Tạo source root và class output riêng cho unit test và integration test.
3. Xây dựng target `compile-main` dùng chung để biên dịch ứng dụng.
4. Tạo các target compile và run riêng cho từng nhóm, với classpath tối thiểu cần thiết.
5. Đưa bước kiểm tra hoặc chuẩn bị môi trường vào nhánh integration test.
6. Tạo các target gọi riêng `test-unit`, `test-integration` và một target tổng hợp `test-all`.
7. Chọn target mặc định phù hợp với vòng lặp phát triển; để integration test được gọi tường minh khi môi trường đã sẵn sàng.
8. Quy định cách tạo fixture và cleanup để test có thể chạy lặp lại.

Đồ thị target nên phản ánh đúng chi phí và dependency thực tế của từng loại kiểm thử. Unit test chỉ cần mã ứng dụng cùng thư viện test; integration test có thêm bước chuẩn bị và dependency ngoài. Khi tách đúng hai nhánh và kết hợp chúng bằng target tổng hợp, Ant có thể chạy kiểm thử nhanh hằng ngày mà vẫn hỗ trợ một lượt kiểm tra tích hợp đầy đủ khi cần.
