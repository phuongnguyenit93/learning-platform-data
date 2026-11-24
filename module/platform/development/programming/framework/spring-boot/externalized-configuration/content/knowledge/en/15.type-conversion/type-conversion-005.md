# Configuring Data Sizes with `DataSize` and `@DataSizeUnit` in Spring Boot

## 1. Problem: Data Capacity Is More Than Just a Number

In Spring Boot, many configuration properties represent **data sizes**: maximum upload file size, buffer limit, threshold for data kept in memory, or size limit for an operation.

If you only use `long` or `int`, a configuration like the following often lacks context:

~~~yaml
app:
  storage:
    upload-buffer: 8
    max-object-size: 64
~~~

Are `8` and `64` in **bytes**, **kilobytes**, or **megabytes**? A deployer may interpret them differently from the author and inadvertently configure a buffer that is far too small or a limit that is far too large.

Spring Framework provides `org.springframework.util.unit.DataSize` to represent sizes in **bytes**. Spring Boot supports converting configuration strings to `DataSize` when binding `@ConfigurationProperties`, with explicit unit notations such as:

~~~properties
app.storage.upload-buffer=8MB
app.storage.max-object-size=64MB
app.storage.memory-threshold=256KB
~~~

When you need a **default unit other than bytes** for suffixless values, Spring Boot provides `org.springframework.boot.convert.DataSizeUnit`:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize uploadBuffer;
~~~

Then `app.storage.upload-buffer=8` is interpreted as **8MB** instead of 8 bytes. If the configuration explicitly states `512KB`, the `KB` suffix determines the unit.

> Two ideas to keep separate: **`DataSize` is the data-size value type**, whereas **`@DataSizeUnit` defines the default unit when a configuration value has no unit**. The annotation does not set a default value for a missing property.

## 2. What Are `DataSize` and `DataUnit`?

Relevant classes:

~~~java
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;
import org.springframework.boot.convert.DataSizeUnit;
~~~

- `DataSize`: an immutable value object representing a size in bytes; provides factory methods such as `ofBytes(...)`, `ofKilobytes(...)`, `ofMegabytes(...)`, `ofGigabytes(...)`, and `ofTerabytes(...)`.
- `DataUnit`: an enum defining the standard units supported by `DataSize`, including `BYTES`, `KILOBYTES`, `MEGABYTES`, `GIGABYTES`, and `TERABYTES`.
- `@DataSizeUnit`: a Spring Boot annotation applied at the binding point to change the default unit of a `DataSize` property when the configuration source contains a number without a suffix.

Example of direct usage in Java:

~~~java
DataSize small = DataSize.ofBytes(512);
DataSize medium = DataSize.ofKilobytes(256);
DataSize large = DataSize.ofMegabytes(10);

long bytes = large.toBytes();
boolean tooBig = large.compareTo(DataSize.ofMegabytes(8)) > 0;
~~~

`DataSize` does not know on its own whether it represents disk capacity, a buffer, HTTP payload, or file size. It only expresses **a size quantity**, while usage and valid limits are defined by the application.

### 2.1. Units Use Binary Multiples

Although the API suffixes are written as `KB`, `MB`, and `GB`, units in `DataUnit` are defined in **powers of 2**, not multiples of 1,000.

| Unit | Suffix | Bytes |
| --- | --- | ---: |
| Byte | `B` | 1 |
| Kilobyte | `KB` | 1,024 |
| Megabyte | `MB` | 1,048,576 |
| Gigabyte | `GB` | 1,073,741,824 |
| Terabyte | `TB` | 1,099,511,627,776 |

Example:

~~~java
DataSize oneKb = DataSize.ofKilobytes(1);
DataSize oneMb = DataSize.ofMegabytes(1);

System.out.println(oneKb.toBytes()); // 1024
System.out.println(oneMb.toBytes()); // 1048576
~~~

This matters when comparing against external systems that follow SI conventions (1 MB = 1,000,000 bytes). In Spring Boot `DataSize` configuration, `1MB` here is 1,048,576 bytes. If an external protocol or service requires exact bytes, convert via `toBytes()` and pass the converted `long` value.

## 3. Data Size Formats Supported by Spring Boot

When binding to a `DataSize` property, Spring Boot understands strings consisting of a number and a supported unit suffix:

~~~properties
app.storage.minimum=512B
app.storage.buffer=8KB
app.storage.cache=64MB
app.storage.quota=2GB
app.storage.archive=1TB
~~~

For a source without a suffix:

~~~properties
app.storage.minimum=512
~~~

if the `minimum` property has type `DataSize` and **no `@DataSizeUnit`**, `512` is interpreted as **512 bytes**.

Illustrative table:

| Config Value | Interpreted Unit | Total Bytes |
| --- | --- | ---: |
| `256` | `B` by default | 256 |
| `256B` | `B` | 256 |
| `2KB` | `KB` | 2,048 |
| `8MB` | `MB` | 8,388,608 |
| `1GB` | `GB` | 1,073,741,824 |
| `1TB` | `TB` | 1,099,511,627,776 |

Choose the standard syntax **integer immediately followed by suffix**, such as `256KB` or `2MB`. Do not assume the parser accepts arbitrary styles like `"2 MB"`, `"1.5MB"`, `"200 MiB"`, or custom unit names. If you need a fractional size, convert it to a smaller unit and write it as an integer—for example, **`1.5MB` can be written as `1536KB`** under binary units.

Values like `0B` or negative numbers can be represented by `DataSize`, but **that does not mean they are valid for every business configuration**. Validate explicit bounds for buffers, upload files, and memory limits.

## 4. Without `@DataSizeUnit`: Bare Numbers Default to Bytes

Suppose an application class has:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    private DataSize memoryThreshold = DataSize.ofBytes(512);

    public DataSize getMemoryThreshold() {
        return memoryThreshold;
    }

    public void setMemoryThreshold(DataSize memoryThreshold) {
        this.memoryThreshold = memoryThreshold;
    }
}
~~~

And YAML:

~~~yaml
app:
  storage:
    memory-threshold: 256
~~~

`memoryThreshold` binds to `DataSize.ofBytes(256)` because **bytes is the default unit**.

Compare:

~~~yaml
# Configuration A:
app:
  storage:
    memory-threshold: 256
~~~

~~~yaml
# Configuration B:
app:
  storage:
    memory-threshold: 256KB
~~~

The two values are not equivalent: A is 256 bytes, while B is 262,144 bytes. That is a 1,024× difference, so omitting a suffix in large-size configs can cause major bugs.

**Recommendation:** if configuration is regularly edited by operators, write suffixes `B`, `KB`, `MB`, or `GB` explicitly to prevent misunderstandings, even when Java already specifies a default-unit annotation.

## 5. Using `@DataSizeUnit` for Suffixless Properties

Suppose teams agree that all suffixless numbers for `upload-buffer` are in megabytes. You can declare:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize uploadBuffer = DataSize.ofMegabytes(2);

    public DataSize getUploadBuffer() {
        return uploadBuffer;
    }

    public void setUploadBuffer(DataSize uploadBuffer) {
        this.uploadBuffer = uploadBuffer;
    }
}
~~~

When the configuration source has:

~~~properties
app.storage.upload-buffer=8
~~~

the binder interprets `8` as **8MB**, or 8,388,608 bytes.

If the configuration changes to:

~~~properties
app.storage.upload-buffer=512KB
~~~

then the effective value is **512KB**, or 524,288 bytes. `@DataSizeUnit(DataUnit.MEGABYTES)` **does not force every value into MB regardless of suffix**. It only supplies the default unit when no suffix is present.

A quick summary table:

| Config Line | Annotation on Field | Result |
| --- | --- | --- |
| `upload-buffer=8` | None | 8 bytes |
| `upload-buffer=8` | `@DataSizeUnit(MEGABYTES)` | 8MB |
| `upload-buffer=8MB` | None | 8MB |
| `upload-buffer=8MB` | `@DataSizeUnit(MEGABYTES)` | 8MB |
| `upload-buffer=512KB` | `@DataSizeUnit(MEGABYTES)` | 512KB |

### 5.1. The Annotation Is Not a Default Value

The two snippets below have different responsibilities:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize uploadBuffer;
~~~

The annotation defines **the unit when suffixless numeric data is supplied**. If `app.storage.upload-buffer` is absent from all sources and there is no initializer, the field can still be `null`.

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
private DataSize uploadBuffer = DataSize.ofMegabytes(2);
~~~

Here `DataSize.ofMegabytes(2)` is what establishes the **2MB** default when the object is created. If the binder receives no override for this field, the initializer can remain intact.

If YAML has `upload-buffer: 8`, the binder overwrites 2MB with 8MB; if YAML does not declare `upload-buffer`, the field can stay 2MB.

## 6. Complete Example: JavaBean `@ConfigurationProperties`

Suppose an application manages three limits:

- `max-object-size`: largest accepted object size.
- `upload-buffer`: buffer size for upload handling.
- `memory-threshold`: threshold for keeping data in RAM before switching strategies.

### 6.1. YAML Configuration

~~~yaml
# src/main/resources/application.yml
app:
  storage:
    max-object-size: 64MB
    upload-buffer: 8
    memory-threshold: 256KB
~~~

Here `upload-buffer: 8` intentionally **omits a suffix** to demonstrate `@DataSizeUnit`. In real operations, `upload-buffer: 8MB` is usually easier to read.

### 6.2. JavaBean Class

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    private DataSize maxObjectSize = DataSize.ofMegabytes(32);

    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize uploadBuffer = DataSize.ofMegabytes(2);

    private DataSize memoryThreshold = DataSize.ofBytes(512);

    public DataSize getMaxObjectSize() {
        return maxObjectSize;
    }

    public void setMaxObjectSize(DataSize maxObjectSize) {
        this.maxObjectSize = maxObjectSize;
    }

    public DataSize getUploadBuffer() {
        return uploadBuffer;
    }

    public void setUploadBuffer(DataSize uploadBuffer) {
        this.uploadBuffer = uploadBuffer;
    }

    public DataSize getMemoryThreshold() {
        return memoryThreshold;
    }

    public void setMemoryThreshold(DataSize memoryThreshold) {
        this.memoryThreshold = memoryThreshold;
    }
}
~~~

### 6.3. Registering the Properties Bean

One way to register:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Or use `@EnableConfigurationProperties(StorageProperties.class)` on a configuration class. Do not both instantiate the bean manually and scan the same type without reason, as doing so can register unwanted duplicate beans.

### 6.4. Result After Binding

| Java Field | Value from YAML | `toBytes()` |
| --- | --- | ---: |
| `maxObjectSize` | `64MB` | 67,108,864 |
| `uploadBuffer` | `8` with `@DataSizeUnit(MEGABYTES)` | 8,388,608 |
| `memoryThreshold` | `256KB` | 262,144 |

A service can inject the bean and read the byte counts:

~~~java
package com.example.service;

import com.example.config.StorageProperties;
import org.springframework.stereotype.Service;

@Service
public class StoragePolicy {
    private final long maxObjectBytes;
    private final long bufferBytes;

    public StoragePolicy(StorageProperties props) {
        this.maxObjectBytes = props.getMaxObjectSize().toBytes();
        this.bufferBytes = props.getUploadBuffer().toBytes();
    }

    public boolean accepts(long incomingBytes) {
        return incomingBytes >= 0 && incomingBytes <= maxObjectBytes;
    }

    public long getBufferBytes() {
        return bufferBytes;
    }
}
~~~

`DataSize` keeps code from manually computing `megabytes * 1024 * 1024` across multiple files. However, checking `incomingBytes` in the business layer does not replace request/body limits enforced by the server or gateway at the HTTP layer.

## 7. Constructor Binding: Placing `@DataSizeUnit` on Parameters

For immutable classes, Spring Boot can bind properties through the constructor instead of calling setters. In that case, `@DataSizeUnit` is placed on the **constructor parameter**:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public final class StorageProperties {

    private final DataSize maxObjectSize;
    private final DataSize uploadBuffer;
    private final DataSize memoryThreshold;

    public StorageProperties(
            @DefaultValue("64MB") DataSize maxObjectSize,
            @DataSizeUnit(DataUnit.MEGABYTES)
            @DefaultValue("2MB") DataSize uploadBuffer,
            @DefaultValue("512B") DataSize memoryThreshold) {
        this.maxObjectSize = maxObjectSize;
        this.uploadBuffer = uploadBuffer;
        this.memoryThreshold = memoryThreshold;
    }

    public DataSize getMaxObjectSize() {
        return maxObjectSize;
    }

    public DataSize getUploadBuffer() {
        return uploadBuffer;
    }

    public DataSize getMemoryThreshold() {
        return memoryThreshold;
    }
}
~~~

In Spring Boot 3.x, a configuration class with a single parameterized constructor can usually use constructor binding without adding `@ConstructorBinding`.

Meaning of each annotation:

- `@DefaultValue("64MB")`: if `max-object-size` is missing, the binder uses 64MB.
- `@DataSizeUnit(DataUnit.MEGABYTES)`: if `upload-buffer` is supplied as a bare number like `8`, the binder interprets it as 8MB.
- `@DefaultValue("2MB")`: if `upload-buffer` **is completely absent**, the binder falls back to 2MB.
- `@DefaultValue("512B")`: if `memory-threshold` is missing, the binder uses 512 bytes.

Note that `@DefaultValue` is constructor-binding metadata, **not** an API that writes default properties into every `PropertySource`.

### 7.1. Registering via the Proper Mechanism

A constructor-bound class must be registered via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(StorageProperties.class)`. Do not create it through a regular `@Bean` factory method and expect Spring Boot to supply all constructor arguments for that instance via dedicated constructor binding.

Explicit registration example:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StorageProperties.class)
public class StorageConfiguration {
}
~~~

If there are multiple overloaded constructors, you may need to mark the constructor to bind with `@ConstructorBinding` on the appropriate **constructor** (per the Spring Boot 3.x API) rather than assuming any constructor can be used.

## 8. `@ConfigurationProperties` Records with `DataSize`

With Java 17+ and Spring Boot 3.x, a record is a concise way to model field-level immutable configuration:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @DefaultValue("64MB") DataSize maxObjectSize,
        @DataSizeUnit(DataUnit.MEGABYTES)
        @DefaultValue("2MB") DataSize uploadBuffer,
        @DefaultValue("512B") DataSize memoryThreshold) {
}
~~~

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(StorageProperties.class)`.

Accessing record components:

~~~java
DataSize limit = props.maxObjectSize();
DataSize buffer = props.uploadBuffer();

long limitBytes = limit.toBytes();
long bufferBytes = buffer.toBytes();
~~~

Record accessors are `maxObjectSize()` and `uploadBuffer()`, not JavaBean getters `getMaxObjectSize()`/`getUploadBuffer()`.

In particular, `@DataSizeUnit(DataUnit.MEGABYTES)` on the record component supplies metadata to the corresponding constructor parameter. With YAML `upload-buffer: 8`, the object receives 8MB; with `upload-buffer: 512KB`, it receives 512KB.

**Note on defaults:** a record has no instance field initializers like a JavaBean; `@DefaultValue` is the explicit way to provide fallbacks for constructor parameters. If a required field has neither configuration nor a default, it can be `null`; add appropriate validation.

## 9. `@DataSizeUnit` and `@DefaultValue` Are Different

This distinction must be clear:

| Tool | When Does It Apply? | Example |
| --- | --- | --- |
| `DataSize` | Specifies the Java data type | `private DataSize buffer;` |
| `@DataSizeUnit(MEGABYTES)` | Property has a number **without a suffix** | `buffer: 8` → 8MB |
| `@DefaultValue("2MB")` | Property **is not provided** in constructor binding | Missing `buffer` → 2MB |
| Java field initializer | JavaBean is instantiated and not overridden | `buffer = DataSize.ofMegabytes(2)` |
| `@NotNull` or custom validation | Requires valid object after binding | Missing/`null` is invalid |

Three scenarios for a record component:

~~~java
@DataSizeUnit(DataUnit.MEGABYTES)
@DefaultValue("2MB")
DataSize uploadBuffer
~~~

1. Configuration source has `upload-buffer: 8` → **8MB** via the MB default unit.
2. Configuration source has `upload-buffer: 512KB` → **512KB** via the explicit suffix.
3. `upload-buffer` is absent → **2MB** via `@DefaultValue`.

Do not say "`@DataSizeUnit(MEGABYTES)` gives the field a default of 1MB." The annotation specifies a unit, not a quantity, and does not alter any initializer you wrote in Java.

## 10. Declaring in `application.properties`, YAML, and Other Sources

### 10.1. Java Properties File

~~~properties
app.storage.max-object-size=64MB
app.storage.upload-buffer=8
app.storage.memory-threshold=256KB
~~~

Values are converted according to field type, annotations, and Spring Boot converters.

### 10.2. YAML File

~~~yaml
app:
  storage:
    max-object-size: "64MB"
    upload-buffer: 8
    memory-threshold: "256KB"
~~~

You can place suffixed strings in double quotes for readability; the bare number `8` is still converted by the binder according to `@DataSizeUnit`. Using YAML quotes does not by itself define a size unit.

### 10.3. OS Environment Variables

With prefix `app.storage` and field `maxObjectSize`, canonical environment variables look like:

~~~bash
APP_STORAGE_MAXOBJECTSIZE=128MB
APP_STORAGE_UPLOADBUFFER=16
APP_STORAGE_MEMORYTHRESHOLD=512KB
~~~

In a Unix shell, you can run:

~~~bash
APP_STORAGE_MAXOBJECTSIZE=128MB APP_STORAGE_UPLOADBUFFER=16 java -jar app.jar
~~~

If no higher-precedence configuration source overrides them, `maxObjectSize` will be 128MB and `uploadBuffer` will be 16MB (assuming the field has `@DataSizeUnit(MEGABYTES)`).

Environment variable naming rule in Spring Boot configuration properties binding: replace dots with underscores, **remove hyphens**, and convert to uppercase. For example:

~~~text
app.storage.upload-buffer   → APP_STORAGE_UPLOADBUFFER
app.storage.max-object-size → APP_STORAGE_MAXOBJECTSIZE
~~~

Do not assume `APP_STORAGE_UPLOAD_BUFFER` is the canonical equivalent for every property name; follow the canonical rule above and verify actual deployments.

### 10.4. Java System Properties and CLI

The same configuration can be supplied via `-D`:

~~~bash
java -Dapp.storage.upload-buffer=10MB -jar app.jar
~~~

Or via a command-line option when enabled:

~~~bash
java -jar app.jar --app.storage.upload-buffer=10MB
~~~

These two forms are **two distinct property sources**. `-D` belongs to JVM system properties, while `--...` belongs to application command-line arguments. `@DataSizeUnit` only decides how **suffixless numeric values** are interpreted; it does not alter source precedence.

## 11. Precedence Rules When Multiple Sources Declare the Same Size

Suppose the file contains:

~~~yaml
app:
  storage:
    max-object-size: 64MB
    upload-buffer: 8
~~~

The runtime environment supplies:

~~~bash
APP_STORAGE_UPLOADBUFFER=16
~~~

And the program is launched with:

~~~bash
APP_STORAGE_UPLOADBUFFER=16 java -jar app.jar --app.storage.upload-buffer=512KB
~~~

In default Spring Boot configuration, with no higher-precedence source present:

- CLI provides `512KB` and typically **takes precedence over** OS environment variables.
- The environment variable provides `16`, but does not win in the run above.
- YAML provides `8`, with lower precedence than the two sources above.

The resulting `uploadBuffer` is **512KB**, not 16MB or 8MB. The explicit `KB` suffix ensures `@DataSizeUnit(MEGABYTES)` does not alter the unit of the winning value.

If CLI is omitted, environment variable `16` can win and bind as **16MB**. If the environment variable is also omitted, YAML `8` can bind as **8MB**.

Result table:

| Sources Present | Winning Value | `uploadBuffer.toBytes()` |
| --- | --- | ---: |
| Only YAML `8` | 8MB via annotation | 8,388,608 |
| YAML `8` + env `16` | 16MB via annotation | 16,777,216 |
| YAML `8` + env `16` + CLI `512KB` | 512KB | 524,288 |

If `SpringApplication` calls `setAddCommandLineProperties(false)` before `run`, standard command-line properties are not added to `Environment`; the result then depends on the remaining sources.

`@DataSizeUnit` neither creates custom precedence nor merges multiple size numbers. Precedence rules and conversion are two separate steps.

## 12. Using `DataSize` in Business Logic

`DataSize` is useful because code can work with a meaningful type instead of unparsed strings.

Example:

~~~java
import org.springframework.util.unit.DataSize;

public final class UploadGuard {
    private final DataSize maxSize;

    public UploadGuard(DataSize maxSize) {
        this.maxSize = maxSize;
    }

    public boolean allows(long incomingSizeBytes) {
        return incomingSizeBytes >= 0
                && incomingSizeBytes <= maxSize.toBytes();
    }
}
~~~

Usage:

~~~java
UploadGuard guard =
        new UploadGuard(DataSize.ofMegabytes(64));

boolean accepted = guard.allows(5L * 1024 * 1024);
~~~

A Spring Boot application can build a bean from properties:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UploadConfiguration {

    @Bean
    UploadGuard uploadGuard(StorageProperties properties) {
        return new UploadGuard(properties.getMaxObjectSize());
    }
}
~~~

The `getMaxObjectSize()` example matches the JavaBean in section 6. If you choose a record, replace it with `properties.maxObjectSize()`.

**Distinction:** `UploadGuard` logic is only an application-level check; it does not automatically cap the bytes accepted by a reverse proxy, web server, or multipart resolver before this code runs.

### 12.1. Comparing `DataSize` Without Converting to a Coarse Unit

You can compare directly:

~~~java
DataSize current = DataSize.ofKilobytes(1536);
DataSize limit = DataSize.ofMegabytes(2);

if (current.compareTo(limit) <= 0) {
    // Current = 1.5MB, smaller than the 2MB limit.
}
~~~

Or use `toBytes()` for exact comparison. Do not convert every value with `toMegabytes()` before comparing when byte-level precision matters, because converting to a larger unit truncates the remainder. For example, `DataSize.ofKilobytes(1536).toMegabytes()` returns the integer **1**, whereas the actual size is 1.5MB.

## 13. Combining with Bean Validation

Successful binding **does not guarantee a business-valid size**. For instance, `0B` or `-5MB` are representable by `DataSize`, yet a negative buffer or zero-byte upload limit may be invalid.

First, you can require the field to be non-null:

~~~java
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import org.springframework.util.unit.DataSize;

@Validated
@ConfigurationProperties(prefix = "app.storage")
public class StorageProperties {
    @NotNull
    private DataSize maxObjectSize;

    // getter and setter
}
~~~

In Spring Boot 3.x, a compatible Bean Validation implementation is needed, usually via `spring-boot-starter-validation`. `@NotNull` does not automatically check `maxObjectSize.toBytes() > 0`; if a positive size is required, use a dedicated validator or explicit checks when creating dependent beans.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.unit.DataSize;

@Configuration(proxyBeanMethods = false)
public class StoragePolicyConfiguration {

    @Bean
    StoragePolicy storagePolicy(StorageProperties properties) {
        DataSize max = properties.getMaxObjectSize();
        DataSize buffer = properties.getUploadBuffer();

        if (max == null || max.toBytes() <= 0) {
            throw new IllegalStateException(
                    "app.storage.max-object-size must be positive");
        }
        if (buffer == null || buffer.toBytes() <= 0) {
            throw new IllegalStateException(
                    "app.storage.upload-buffer must be positive");
        }
        if (buffer.compareTo(max) > 0) {
            throw new IllegalStateException(
                    "app.storage.upload-buffer must not exceed max-object-size");
        }

        return new StoragePolicy(max, buffer);
    }
}
~~~

Here `StoragePolicy` is an illustrative business class taking two `DataSize` values. Creating this bean assumes a corresponding implementation; the key point is that **constraints are checked after configuration has bound**.

In a production system, you can apply a custom Jakarta constraint for cross-field validation or constructor validation with clear error messages. Do not put `@Min(1)` directly on `DataSize` assuming Bean Validation will interpret it as bytes; `@Min` is designed for supported numeric types, while `DataSize` is its own value type.

### 13.1. Do Not Use Negative Sizes as "Unlimited" Without a Contract

Some library APIs or servers accept `-1` to mean unlimited, but **that is a specific API convention**, not the general meaning of `DataSize.ofBytes(-1)`. Do not define "negative means unlimited" across every `DataSize` property.

If business configuration requires "unlimited", model it explicitly with a boolean/enum or document the receiving component's specific semantics.

## 14. Real-World Example with Multipart Upload Limits

Spring Boot has multipart properties to tune file uploads, such as:

~~~properties
spring.servlet.multipart.max-file-size=10MB
spring.servlet.multipart.max-request-size=20MB
~~~

In a Spring MVC application with multipart support enabled, these values control the upload limits Spring Boot configures for multipart handling.

Distinguish the two levels:

- `max-file-size`: limit for a single file in a multipart request.
- `max-request-size`: limit for the total size of a multipart request.

An HTTP request can carry multiple files and form fields, so `max-request-size` has a different meaning from `max-file-size`.

If the application has its own policy `app.storage.max-object-size=64MB`, that custom property **does not automatically** override `spring.servlet.multipart.max-file-size`. You must configure the right infrastructure properties and align business logic accordingly.

Example:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB

app:
  storage:
    max-object-size: 8MB
    upload-buffer: 2MB
~~~

In this example, business policy sets an 8MB object limit while the multipart layer allows files up to 10MB. Clarify requirements and ensure clients receive appropriate error responses when limits are exceeded.

If a reverse proxy, ingress controller, or API gateway sits in front of the application, request size limits at that layer also apply independently.

## 15. Avoid Confusing `DataSize` with `Duration`

Spring Boot supports several unit-aware configuration conversions. Two commonly confused types:

| Characteristic | `DataSize` | `Duration` |
| --- | --- | --- |
| Quantity | Data capacity | Time span |
| Package | `org.springframework.util.unit.DataSize` | `java.time.Duration` |
| Default-unit annotation | `@DataSizeUnit` | `@DurationUnit` |
| Example units | `B`, `KB`, `MB`, `GB`, `TB` | `ns`, `us`, `ms`, `s`, `m`, `h`, `d` |
| Without a suffix | Defaults to bytes | Defaults to milliseconds |
| Human-readable value | `16MB` | `10s` |

Example configuration class using both:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.boot.convert.DurationUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;
import java.time.temporal.ChronoUnit;

@ConfigurationProperties(prefix = "app.transfer")
public class TransferProperties {
    @DataSizeUnit(DataUnit.MEGABYTES)
    private DataSize bufferSize = DataSize.ofMegabytes(4);

    @DurationUnit(ChronoUnit.SECONDS)
    private Duration timeout = Duration.ofSeconds(15);

    // getters and setters
}
~~~

YAML:

~~~yaml
app:
  transfer:
    buffer-size: 8
    timeout: 30
~~~

`buffer-size: 8` is interpreted as 8MB; `timeout: 30` is interpreted as 30 seconds. Even though both are suffixless numbers, the annotations specify **two different kinds of units**.

If written explicitly as `buffer-size: 512KB` and `timeout: 500ms`, those explicit suffixes are used.

## 16. Reading and Parsing `DataSize` in Java Code

Outside Spring Boot binding, Spring Framework allows parsing a size in Java:

~~~java
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

DataSize a = DataSize.parse("12KB");
DataSize b = DataSize.parse("5MB");
DataSize c = DataSize.parse("20");
DataSize d = DataSize.parse("20", DataUnit.KILOBYTES);

System.out.println(a.toBytes()); // 12288
System.out.println(b.toBytes()); // 5242880
System.out.println(c.toBytes()); // 20
System.out.println(d.toBytes()); // 20480
~~~

Factory methods create values without string parsing:

~~~java
DataSize byteSize = DataSize.ofBytes(512);
DataSize kiloSize = DataSize.ofKilobytes(256);
DataSize megaSize = DataSize.ofMegabytes(8);
DataSize custom = DataSize.of(3, DataUnit.GIGABYTES);
~~~

Useful methods:

| Method | Meaning |
| --- | --- |
| `toBytes()` | Returns byte count as `long` |
| `toKilobytes()` | Converts to whole KB |
| `toMegabytes()` | Converts to whole MB |
| `toGigabytes()` | Converts to whole GB |
| `compareTo(other)` | Compares two sizes |
| `isNegative()` | Checks whether the size is negative |

`DataSize` stores byte counts as `long`. When working with huge numbers, consider representation limits and overflow before adding or multiplying sizes beyond safe ranges.

Do not write naive custom size parsers like "strip the last two characters and multiply by 1,000" when `DataSize` and Spring Boot's binder already exist; hand-rolled parsers easily get suffixes, byte/binary unit differences, and numeric bounds wrong.

## 17. Testing Binding with `ApplicationContextRunner`

When a configuration uses both suffixes and `@DataSizeUnit`, write unit/integration tests covering key inputs.

Minimal example using a record dedicated to testing:

~~~java
package com.example.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        @DataSizeUnit(DataUnit.MEGABYTES) DataSize uploadBuffer,
        DataSize memoryThreshold) {
}
~~~

Verify in a test with `spring-boot-starter-test`:

~~~java
package com.example.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.context.ConfigurationPropertiesAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StoragePropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                    ConfigurationPropertiesAutoConfiguration.class))
                .withUserConfiguration(TestConfiguration.class);

    @Test
    void interpretsDefaultUnitAndExplicitSuffix() {
        runner
            .withPropertyValues(
                "app.storage.upload-buffer=8",
                "app.storage.memory-threshold=256KB")
            .run(context -> {
                assertThat(context).hasNotFailed();
                StorageProperties props =
                        context.getBean(StorageProperties.class);

                assertThat(props.uploadBuffer().toBytes())
                        .isEqualTo(8L * 1024 * 1024);
                assertThat(props.memoryThreshold().toBytes())
                        .isEqualTo(256L * 1024);
            });
    }

    @Test
    void explicitUnitOverridesDefaultUnit() {
        runner
            .withPropertyValues(
                "app.storage.upload-buffer=512KB",
                "app.storage.memory-threshold=10")
            .run(context -> {
                StorageProperties props =
                        context.getBean(StorageProperties.class);

                assertThat(props.uploadBuffer().toBytes())
                        .isEqualTo(512L * 1024);
                assertThat(props.memoryThreshold().toBytes())
                        .isEqualTo(10);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(StorageProperties.class)
    static class TestConfiguration {
    }
}
~~~

The test configuration here places annotations on the record to verify both properties bind to `DataSize`. `ApplicationContextRunner` runs a lightweight context with specific property values, making it easy to verify suffixless numbers, explicit suffixes, and malformed inputs.

For a module with strict rules, add tests for **missing properties**, **negative values**, **zero values**, **exceeding thresholds**, and **higher-precedence source overrides**. These cases belong to business validation, not everything checked automatically by the `DataSize` converter.

## 18. Troubleshooting When Data Size Conversion Fails

Common symptoms:

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| `buffer-size: 8` becomes 8 bytes instead of 8MB | Field lacks `@DataSizeUnit` | Write `8MB` explicitly or put the annotation on the right field/parameter |
| `@DataSizeUnit` is present, yet missing config is still `null` | Annotation sets unit only, not default value | Use a field initializer or `@DefaultValue` for constructor binding |
| `buffer-size: 512KB` does not become 512MB | `KB` suffix is an explicit unit | Expected behavior: explicit suffix beats default unit |
| `memory-threshold: 1.5MB` causes a conversion error | Decimal notation is not standard integer format | Write `1536KB` |
| `max-object-size: 64 MB` fails | Space between number and suffix is non-standard | Use `64MB` |
| Wrong value type prevents app from starting | Cannot convert string to `DataSize` | Fix key/value and inspect the binding message |
| Number is too large | Exceeds byte capacity representable by `long` | Enforce bounds and pick sensible sizes |
| Behavior differs between dev and prod profiles | Property sources have different precedence | Inspect profile files and overriding sources |
| Environment variable has no effect | Env var name does not match canonical relaxed binding | Use `APP_STORAGE_UPLOADBUFFER` per the rule |
| Size bound properly, yet requests still fail | Web server, proxy, or multipart has its own limit | Check both HTTP layer and business policy |

### 18.1. Inspecting Effective Values

In a development environment, you can inject the configuration bean and inspect byte counts:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StorageDebugConfiguration {

    @Bean
    ApplicationRunner printStorageLimits(StorageProperties props) {
        return args -> {
            System.out.println("maxObjectBytes="
                    + props.getMaxObjectSize().toBytes());
            System.out.println("uploadBufferBytes="
                    + props.getUploadBuffer().toBytes());
        };
    }
}
~~~

This snippet assumes you are using the `StorageProperties` JavaBean from section 6. If using a record, switch to record accessors. The example contains no secrets; in real applications avoid logging sensitive values or unnecessary infrastructure details.

Spring Boot Actuator can expose `/actuator/env` and `/actuator/configprops` when enabled, helping identify property sources and bound values. Enable and restrict access according to security policy; never expose endpoints publicly if they could leak configuration details.

## 19. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`DataSize` is just a renamed `long`." | It is a value type representing data size with factory, parsing, conversion, and comparison support. |
| "The number `10` automatically means 10MB." | Without an annotation, the default unit of `DataSize` is bytes. |
| "`@DataSizeUnit(MEGABYTES)` makes every input MB." | It only sets the unit when input lacks a suffix; `256KB` remains KB. |
| "This annotation sets a 1MB default when the property is missing." | No. Use an initializer or `@DefaultValue` for fallback values. |
| "`1MB` always equals 1,000,000 bytes." | In Spring's `DataUnit`, `1MB` equals 1,048,576 bytes. |
| "`toMegabytes()` always performs exact decimal division." | It returns an integer; use `toBytes()` or `compareTo` when byte precision is needed. |
| "`-1B` always means unlimited." | Negative semantics depend on the consuming API; `DataSize` does not define a universal unlimited value. |
| "`@Min(1)` on `DataSize` checks positivity." | Use a type-compatible constraint or custom validation using `toBytes()`. |
| "Setting `app.storage.max-object-size` automatically blocks multipart uploads." | Custom properties only take effect where the app reads them; the HTTP layer has its own properties. |
| "Using a record means `@DataSizeUnit` cannot be applied." | The annotation can be placed on the record component/constructor parameter for binding. |
| "`@DataSizeUnit` changes property source precedence." | No, it only affects the unit during conversion. |

## 20. Practice Exercises

### 20.1. Problem Statement

Given the record:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.convert.DataSizeUnit;
import org.springframework.util.unit.DataSize;
import org.springframework.util.unit.DataUnit;

@ConfigurationProperties(prefix = "app.cache")
public record CacheProperties(
        @DataSizeUnit(DataUnit.MEGABYTES)
        @DefaultValue("4MB") DataSize entryLimit,
        @DefaultValue("512KB") DataSize writeBuffer,
        DataSize minimumFreeSpace) {
}
~~~

File `application.yml`:

~~~yaml
app:
  cache:
    entry-limit: 10
    write-buffer: 2MB
    minimum-free-space: 1GB
~~~

**Question 1:** How many bytes is `entryLimit`?

**Answer:** 10MB = **10,485,760 bytes**, because `@DataSizeUnit(MEGABYTES)` interprets the bare number `10`.

**Question 2:** How many bytes is `writeBuffer`?

**Answer:** 2MB = **2,097,152 bytes**, because the `MB` suffix is written explicitly.

**Question 3:** How many bytes is `minimumFreeSpace`?

**Answer:** 1GB = **1,073,741,824 bytes**, because the `GB` suffix is provided.

**Question 4:** What happens if you remove `entry-limit` from YAML while keeping the record?

**Answer:** the default value is 4MB via `@DefaultValue("4MB")`; `@DataSizeUnit` is not a source of defaults.

**Question 5:** What happens if you change `entry-limit: 10` to `entry-limit: 512KB`?

**Answer:** the value is 512KB = **524,288 bytes**. The MB annotation does not override an explicit suffix unit.

**Question 6:** If you add environment variable `APP_CACHE_ENTRYLIMIT=20MB` and CLI `--app.cache.entry-limit=8MB` with command-line properties enabled, what is the result?

**Answer:** with standard sources and no higher-precedence override, CLI wins so `entryLimit=8MB`. 8MB is not added to 20MB or to 10MB in YAML.

### 20.2. Applied Exercise

Create an `@ConfigurationProperties(prefix = "app.archive")` class containing:

- `segmentSize`: defaults to 8MB, while allowing `segment-size: 16` to mean 16MB.
- `maxArchiveSize`: required, must be written explicitly such as `2GB`.
- `minFreeSpace`: defaults to 512KB.

Then write a validator ensuring:

~~~text
segmentSize > 0
maxArchiveSize > 0
minFreeSpace >= 0
segmentSize <= maxArchiveSize
~~~

Hint: use `DataSize.of...(...)`, `@DataSizeUnit(DataUnit.MEGABYTES)`, `@DefaultValue` if using constructor binding, `toBytes()` or `compareTo(...)` when comparing, and check for null before reading.

## 21. Key Takeaways

1. **`DataSize`** is a size value type in Spring Framework, representing exact byte counts and supporting conversion from `B`, `KB`, `MB`, `GB`, and `TB` suffixes.
2. **Suffixless numbers default to bytes.** Thus `8` is completely different from `8MB`.
3. **`@DataSizeUnit`** changes the default unit when binding a suffixless value—for instance, `@DataSizeUnit(MEGABYTES)` turns `8` into 8MB.
4. **Explicit suffixes win:** `512KB` is always 512KB, even if the annotation specifies MB as the default.
5. **`@DataSizeUnit` does not supply a fallback value when a property is absent.** Use a JavaBean initializer or `@DefaultValue` for constructor/record binding.
6. **Sizes in `DataUnit` use powers of 2:** `1KB=1,024B` and `1MB=1,048,576B`.
7. **Validation is a separate responsibility:** `DataSize` alone does not guarantee positive values, RAM budget compliance, upload thresholds, or infrastructure policies.
8. **Distinguish `DataSize` and `Duration`:** one represents capacity, the other time duration; their default-unit annotations differ as well.
9. **All config data sources still follow `Environment` precedence:** conversion to `DataSize` occurs after the effective source and value have been determined.

### References

- Spring Boot Reference — Externalized Configuration, Converting Data Sizes: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.conversion.data-sizes
- Spring Boot 3.3 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Javadoc — DataSize: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/unit/DataSize.html
- Spring Framework Javadoc — DataUnit: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/unit/DataUnit.html
- Spring Boot Reference — Properties Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation