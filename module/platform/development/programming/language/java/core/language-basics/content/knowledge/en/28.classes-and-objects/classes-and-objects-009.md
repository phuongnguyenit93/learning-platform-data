# From a `main`-Only Program to a Multi-Class Program — Java 17+

> **Java core — language-basics / Classes and Objects**  
> **Requirements:** JDK 17+, no external libraries or build tools.  
> **Goal:** Know when a single-`main` program becomes hard to maintain; move related data and behavior into separate classes; create objects with `new`, invoke methods via dot notation, compile multiple `.java` files, and run the class containing `main`.

## 1. Why Start with Just One `main`?

A very small Java program can place all its work inside `main`:

~~~java
public final class Hello {
    public static void main(String[] args) {
        String name = "Lan";
        System.out.println("Hello " + name);
    }
}
~~~

`main(String[] args)` is the familiar entry point when running a class via `java Hello`. It is a `static` method because the Java launcher does not need to create a `Hello` object to invoke this entry point.

When an application only performs a few sequential statements, a short, clear `main` makes sense. However, if `main` stores data, validates inputs, performs calculations, and prints to the screen all at once, future changes will easily affect many unrelated parts.

This lesson uses the same simple requirement for both versions:

- There are two students: **Lan** with score 7, **Minh** with score 9.
- Add 1 point to Lan.
- Print each student's score and the class average.

The output of both versions must be **identical**; the goal of splitting classes is better structure, not changing business behavior.

## 2. First Version: All Logic Inside `main`

Create file **MainOnly.java**:

~~~java
public final class MainOnly {
    public static void main(String[] args) {
        String[] names = {"Lan", "Minh"};
        int[] scores = {7, 9};

        // Update Lan's score.
        scores[0] += 1;

        // Print each student's score.
        for (int i = 0; i < names.length; i++) {
            System.out.println(names[i] + "=" + scores[i]);
        }

        // Compute and print the average score.
        int total = 0;
        for (int score : scores) {
            total += score;
        }
        System.out.println("average=" + (double) total / scores.length);
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 MainOnly.java
java MainOnly
~~~

**Exact expected stdout:**

~~~text
Lan=8
Minh=9
average=8.5
~~~

The syntax `(double) total / scores.length` ensures division yields a decimal result; using `int / int` would perform integer division and drop the fractional part.

The single-class version is **not wrong**. However, when you need to add students, validate scores from 0 to 10, store additional information, or reuse the average calculation across multiple places, those lines of code begin to cause problems:

| Current part | Problem when scaling |
| --- | --- |
| `names[i]` and `scores[i]` | Two parallel arrays must always stay the same length and aligned by index |
| `scores[0] += 1` | Any code snippet can assign an out-of-range score |
| Score-printing loop | Presentation logic and data processing are mixed in `main` |
| Average calculation | Easy to end up copying it when another screen/feature needs it too |
| Index `0` tied to Lan | Changing student order could cause updates to hit the wrong person |

Improvement direction: group **name + score + score-change rules** into a `Student` object; group **student list + average calculation + printing list** into a `Classroom` object; keep `main` in the coordinator class `SchoolApp`.

## 3. Identifying Each Class's Responsibility

| Class | State / Role | Main behavior |
| --- | --- | --- |
| `Student` | Name and score of **one student** | Create student, read name/score, increase score with validation |
| `Classroom` | Student references in **one classroom** | Print list and compute average score |
| `SchoolApp` | Program entry point | Create objects, coordinate calls, print overall results |

Simple folder layout, all files in the same directory and **no `package` declaration** in the example:

~~~text
study/
├── MainOnly.java      # Single-main version for comparison.
├── Student.java       # Student object.
├── Classroom.java     # Student list and calculations.
└── SchoolApp.java     # Main coordinating the multi-class version.
~~~

You can keep `MainOnly.java` for comparison; when running `SchoolApp`, the JVM does not automatically execute `MainOnly.main`.

Having many classes does not automatically make a program "good object-oriented design". Only extract a class when it has a **clear responsibility**; avoid creating classes that merely forward a single line without making the code clearer.

## 4. Extracting One Student into `Student.java`

Create file **Student.java**:

~~~java
public final class Student {
    private final String name;
    private int score;

    public Student(String name, int score) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (score < 0 || score > 10) {
            throw new IllegalArgumentException("score must be 0..10");
        }
        this.name = name;
        this.score = score;
    }

    public String name() {
        return name;
    }

    public int score() {
        return score;
    }

    public void improve(int points) {
        if (points < 0 || points > 10 - score) {
            throw new IllegalArgumentException("invalid improvement");
        }
        score += points;
    }
}
~~~

Explanation:

1. `class Student` creates a **new reference type** named `Student`. Each `new Student("Lan", 7)` creates a new **student object**.
2. `private final String name` and `private int score` are **instance fields**. Each object holds its own values; code in other classes cannot access `private` fields directly.
3. The constructor `Student(String name, int score)` validates input and initializes fields via `this.name = name` and `this.score = score`.
4. `name()`, `score()`, and `improve(int points)` are **instance methods**; they require an object receiver, such as `lan.improve(1)`.
5. `improve` enforces the rule that score cannot exceed 10. Using `points > 10 - score` instead of `score + points > 10` avoids large integer addition overflowing before the check.
6. `final` on `name` forbids changing the **name reference** after initialization. `score` is not `final` because business logic allows increasing the score. `final class Student` at the top prevents subclassing; it does not automatically make every `Student` object immutable.

Placing validation logic in the `Student` class saves callers from repeating the same rules whenever scores change.

**Call example:** `Student lan = new Student("Lan", 7);` then `lan.improve(1);`, and `lan.score()` returns `8`. Creating `Student minh = new Student("Minh", 9);` does not affect the `lan` object.

## 5. Creating `Classroom.java` to Manage Multiple Students

Create file **Classroom.java**:

~~~java
public final class Classroom {
    private final Student[] students;

    public Classroom(Student[] students) {
        if (students == null || students.length == 0) {
            throw new IllegalArgumentException("students must not be empty");
        }

        this.students = students.clone();

        for (Student student : this.students) {
            if (student == null) {
                throw new IllegalArgumentException("student must not be null");
            }
        }
    }

    public void printScores() {
        for (Student student : students) {
            System.out.println(student.name() + "=" + student.score());
        }
    }

    public double average() {
        int total = 0;
        for (Student student : students) {
            total += student.score();
        }
        return (double) total / students.length;
    }
}
~~~

`Classroom` uses `Student[]` because there is now a class describing **one student**, eliminating the need to maintain two parallel arrays `String[]` and `int[]`. It focuses on operations concerning **the whole class**.

- The constructor receives a `Student[]` array and calls `students.clone()` to **copy the outer array**, preventing callers from reordering elements in the input array and altering the internal list.
- The **`Student` objects are not cloned** by the array's `clone()`: both arrays still hold references to the same objects. Therefore, if `lan.improve(1)` is called, the classroom sees the updated score.
- The loop checking for no `null` elements lets `printScores()` and `average()` safely invoke methods on each `Student`.
- `average()` never divides by 0 because the constructor already rejected empty arrays.
- `printScores()` illustrates printing for this lesson; in an application with a complex UI, you can separate display logic and have `Classroom` return data.

Declaring `students` as `final` means this field variable cannot be reassigned to another array after initialization; it does **not** mean every element or `Student` state is immutable.

## 6. `SchoolApp.java`: `main` Only Coordinates Objects

Create file **SchoolApp.java**:

~~~java
public final class SchoolApp {
    public static void main(String[] args) {
        Student lan = new Student("Lan", 7);
        Student minh = new Student("Minh", 9);

        Classroom classroom =
                new Classroom(new Student[] {lan, minh});

        lan.improve(1);
        classroom.printScores();

        System.out.println("average=" + classroom.average());
    }
}
~~~

This version performs the exact same steps as `MainOnly`, yet `main` does not need to know how scores are stored or how the average is summed:

~~~text
SchoolApp.main(...)
   |
   +--> new Student("Lan", 7)
   +--> new Student("Minh", 9)
   +--> new Classroom(Student[] {lan, minh})
   |
   +--> lan.improve(1)
   +--> classroom.printScores()
   +--> classroom.average()
~~~

In `classroom.printScores()`, the dot `.` denotes calling a **method on the `classroom` object**; similarly, `lan.improve(1)` calls a method on the `Student` object referenced by `lan`. `Student[]` is an array holding **`Student` references**, not a classroom type with built-in printing/averaging capabilities.

`SchoolApp.main` is `static` because it is the entry point; it **is allowed to create objects and call instance methods through references**, rather than being forbidden from all instance method calls because of `static`.

## 7. Compiling and Running a Multi-Class Program

Place `Student.java`, `Classroom.java`, and `SchoolApp.java` in the same directory. In a terminal open in that directory, run the following commands; filenames **must** match the `public` top-level class names:

~~~bash
javac -encoding UTF-8 Student.java Classroom.java SchoolApp.java
java SchoolApp
~~~

**Exact expected stdout of `java SchoolApp`:**

~~~text
Lan=8
Minh=9
average=8.5
~~~

The output is **identical to `MainOnly`**. Compiling multiple files produces `Student.class`, `Classroom.class`, and `SchoolApp.class` in the current directory. `javac` needs to locate classes that reference one another; listing all three files as above is the simplest and clearest way for beginners.

You can compile into a separate output directory; create `out` first and run the class name from the classpath root:

~~~bash
javac -encoding UTF-8 -d out Student.java Classroom.java SchoolApp.java
java -cp out SchoolApp
~~~

In this command, **the `out` directory must already exist** before passing it to `javac -d`. On Bash/Linux/macOS you can create it with `mkdir -p out`; on PowerShell: `New-Item -ItemType Directory -Force out | Out-Null`. This is an option to keep `.class` files separate from source files, not required if you use the first pair of commands.

**The command `java SchoolApp` selects one exact entry point:** the JVM does not sequentially run every `main` method across all present classes. If you want to run the old version, run `java MainOnly` separately (after compiling `MainOnly.java`).

The example above is in the **unnamed package** to focus on the transition from one class to multiple classes. In larger projects, organize by `package` and use `javac -d`/`java -cp` with **fully qualified class names**; moving into packages does not change object responsibilities.

## 8. Object Relationships and Reference Variables After Splitting Classes

Code snippet:

~~~java
Student lan = new Student("Lan", 7);
Student minh = new Student("Minh", 9);
Student[] list = {lan, minh};
Classroom room = new Classroom(list);
~~~

You can visualize it as:

~~~text
lan -------> Student(name="Lan", score=7) <------ list[0]
                           ^
                           |
                      room.students[0]

minh ------> Student(name="Minh", score=9) <----- list[1]
                           ^
                           |
                      room.students[1]
~~~

`room.students` is a separate array created by `clone()`, yet its elements reference **the same two `Student` objects**. Therefore:

- `lan.improve(1)` causes `room.average()` to use Lan's new score of 8.
- `list[0] = new Student("Hoa", 10)` **does not automatically change** `room.students[0]` because the classroom copied the input array's slots.
- `Student alias = lan; alias.improve(1)` continues modifying **the same Lan object**; assigning `alias = new Student(...)` only changes the `alias` variable.
- Passing `null` instead of an array to the constructor, or leaving an element `null`, causes the constructor to reject it with `IllegalArgumentException` before other methods use the data.

Distinguishing **reference variables**, **objects**, and **reference arrays** helps avoid the misconception that passing objects into a constructor creates a deep copy of all data.

## 9. Safe Refactoring Steps and Common Mistakes

When migrating from one long `main` to multiple classes, you can follow this sequence:

1. **Keep the output behavior as a baseline.** Compile/run the original version and record test cases, including invalid inputs if any.
2. **Group data that always goes together.** Here `name` and `score` belong to one student, so they are kept in `Student` instead of two parallel arrays.
3. **Move behavior tied to data into that class.** Changing and validating scores belongs to `Student.improve`; computing the average belongs to `Classroom.average`.
4. **Keep `main` as the place for instantiation and coordination.** Create `new Student(...)` and pass them to `Classroom`; call methods with clear responsibilities.
5. **Compile all related classes and compare results.** The new version must produce equivalent business results without unintended changes.
6. **Split further only when justified.** Not every method, variable, or small calculation needs its own class.

| Mistake | Understanding / Fix |
| --- | --- |
| Making all fields `public` so `main` can edit them directly | Prefer `private` fields and APIs with clear contracts |
| Trying to call `Student.improve(1)` | `improve` is an instance method; call it on an object such as `lan.improve(1)` |
| Writing `new Student(...)` but calling `new Classroom()` when no no-arg constructor exists | Must use the declared constructor |
| Having two `public` top-level classes in the same `.java` file | Split into files matching class names, or use another valid organization |
| Compiling only `SchoolApp.java` when dependent sources are not found | Specify all source files or configure sourcepath/classpath properly |
| Running `java Student` even though `Student` has no `main` | Run `java SchoolApp`, the class containing the entry point |
| Assuming `clone()` on `Student[]` also copies each `Student` | `clone()` only copies the array; element references remain shared |
| One class holding UI, data, file storage, and all calculations | Consider splitting responsibilities, without dividing mechanically |
| Output differs from the initial `main` version | Re-check input data, state mutation order, and calculations |

### Exercises

**Exercise 1.** Add a student `Student("Hoa", 10)` to the `Classroom` input, predict the average score, and verify by running the program.

**Exercise 2.** Call `lan.improve(3)` when Lan currently has 8. Why is it rejected? Analyze which class owns the validation responsibility.

**Exercise 3.** Write a method `isPassing()` in `Student` requiring a score of 5 or higher. Does `SchoolApp` need to change to know how scores are compared?

**Exercise 4.** Add `highestScore()` to `Classroom`. Explain why a class-wide calculation belongs in `Classroom` rather than in individual `Student` objects.

**Exercise 5.** Create `Student[] input = {lan, minh}`; pass it into `Classroom`, then assign `input[0] = new Student("Hoa", 10)`. Why does the classroom's list not change from this assignment, while `lan.improve(1)` is still observed by the classroom?

### Takeaways

**`main` is the entry point; it does not need to hold the entire program's logic.** Starting with a simple `main` is reasonable; as data and behavior grow, split them into classes with clear responsibilities, keep state behind `private` fields, create objects with `new`, and invoke instance methods through reference variables. Classes can live in separate `.java` files and be compiled together; when running, specify the class containing `main`. The goal of splitting classes is to **preserve behavior, reduce coupling, and make code easier to extend/test**, not to inflate the number of classes for appearances.